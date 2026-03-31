# OpenClaw / Bybit AI Agent 交易系统
# CLAUDE.md — 主项目日志（Claude Code 项目指令文件）
# 备注：本文件即"主日志"，GitHub 根目录 README.md 为"Git 日志"
# 最后更新：2026-03-31（Wave 5 多 Agent 正式落地 + H1-H5 接通 · 2610 tests · demo_only 模式）

---

## 一、项目定位

长期进化型 AI Agent 自动交易系统。OpenClaw 为中枢、Bybit 为主交易所。

> Agent 自主完成交易决策与执行，对成本与收益有清晰感知，能感知自身状态，能持续学习，在严格风控框架下逐步赢得更高自主权。

人类 Operator 角色：不定时检查、审阅、矫正、批准关键步骤、推动策略演进。

**系统管线：** 市场数据 → H0 本地判断 → H1-H5 AI 治理 → I Decision Lease → 执行适配层 → 学习/归因

**详细能力目标（A-J）见：** `docs/references/2026-03-27--system_reference_handbook.md` 第一章

---

## 二、16 条根原则（DOC-01 项目宪法 §5.1–§5.16，不可违背）

**V1 原版（§5.1–§5.10）：**
1. **单一写入口** — 所有订单/执行动作通过唯一受控入口
2. **读写分离** — 研究/GUI/学习：只读。写入权限极度受限、可审计、可锁定
3. **AI 输出 ≠ 即时命令** — AI → Decision Lease（带时效、可撤销）→ 本地复核 → 执行
4. **策略不能绕过风控** — 所有交易意图必须经 Guardian 审批
5. **生存 > 利润** — 先判断"不会螺旋崩溃"，再判断"能否盈利"
6. **失败默认收缩** — 不确定时默认保守：不开新仓、降频率、降风险
7. **学习 ≠ 改写 Live** — 学习平面与 Live 平面隔离
8. **交易可解释** — 每笔交易必须可重建：为什么、何时、风控审批、授权、执行、结果
9. **交易所灾难保护** — 本地止损 + 交易所条件单双重防线
10. **认知诚实** — 所有结论区分事实 / 推断 / 假设

**V2 新增（§5.11–§5.16）：**
11. **Agent 最大自主权** — P0/P1 硬边界内，Agent 完全自主决定：币种、策略、参数、时机
12. **持续进化** — 系统必须从交易行为中自动学习
13. **AI 资源成本感知** — 每次 AI 调用计费，cost_edge_ratio ≥ 0.8 → 建议关仓
14. **零外部成本可运行** — 基础运营仅需 L0+L1（Ollama + 免费搜索）
15. **多 Agent 协作** — OpenClaw 指挥官 + 6 Agent，正式对象通信
16. **组合级风险意识** — 监控关联曝险、策略重叠持仓、资金分配合理性

**优先级序：** 账户生存 > 风控治理 > 系统健康 > 审计可追溯 > 人类终审 > 真实 Net PnL > 自主能力进化

---

## 三、当前系统状态（2026-03-31 Wave 5 多 Agent 正式落地 + H1-H5 接通全部完成）

```
测试：2,610 passed（Wave 5 Sprint 0+5a+5b 全部完成後，18 pre-existing failures）
路由：126+ 条（含 8 治理 + 5 Scout 端点）
治理：GovernanceHub 4 SM 已接入运行时（SM-01/SM-02/SM-04/EX-04），fail-closed 已验证
GUI：11-Tab 专业控制台 + 中文状态 + 悬停提示 + 确认弹窗 + 6 AI 供应商
Bybit Demo：双重执行（Paper Engine + Bybit sandbox）
L1 本地推理：Ollama HTTP 客户端 + Qwen 3.5 9B（快速路径，think=False，~1.9s）/ 27B（复杂任务，~9.9s）
5-Agent 体系：Scout + Strategist + Guardian + Analyst + Executor 全部运行
GUI：11-Tab 专业控制台（实盘锁 + 测试交易双子Tab + tab-live占位 + tab-trading iframe包装）
周报：周三 UTC 0:00 简报（27B Ollama）/ 周日 UTC 0:00 详报（Claude L2）
市场流：后台常驻（BTCUSDT+ETHUSDT 服务启动即开始，不依赖 Paper/Demo 会话状态）

★ Round 2 冷酷功能审核结论（2026-03-30 PM 4 路并行代码级审计）：

  代码完成度            ≈ 80%
  业务功能真正能用      ≈ 45%（自动扫描→策略→风险→下单→止损→学习→进化 全链路评估，Wave 5 後更新）

  逐环节完成度：
    自动扫描              = 90%（ScoutWorker 30min 定時掃描 + Scout→Strategist bus 鏈路已接通）
    策略选择              = 40%（标准技术指标，无 AI、无回测、无动态仓位）
    AI 风险评估           = 55%（H0+H1+H2+H3+H4+H5 全部接通，shadow=False，acquire_lease 前置）
    下单                  = 90%（治理 gate + OMS SM-03 + ExecutorAgent 包装，Batch 11）
    止损                  = 90%（本地 3 类止损 + 交易所条件单双重防线，Batch 11）
    学习                  = 25%（E1 观察 + L2 自动触发 + Sunday cron，Batch 10）
    进化                  = 30%（PaperLiveGate 已部署，11 项准入评估 + API 端点 + 日报自动化，无策略自动优化）

  关键发现：
    ✅ 治理 fail-closed 一流（is_authorized 真实拒绝订单，acquire_lease fail-closed）
    ✅ P0/P1/P2 风控真实执行（check_order_allowed 返回 False 阻止订单）
    ✅ 异常处理防御性、核心代码零 except:pass
    ✅ 5/6 Agent 已实现（Scout/Strategist/Guardian/Analyst/Executor，仅 Conductor 编排待完善）
    ✅ Conductor 注册 5 个 Agent，MessageBus 有多订阅者
    ✅ ExecutorAgent 接入管线：APPROVED_INTENT→submit_order()→EXECUTION_REPORT（Batch 11）
    ✅ L2 AI Engine 自动触发（Batch 10：observations≥200 auto + Sunday cron）
    ❌ Perception Plane register_data() 零调用
    ✅ OMS SM-03 已串联（Batch 10：Paper 7-state→OMS 11-state 映射，fail-closed）
    ✅ PaperLiveGate 已部署（Batch 12：11 项准入评估 + GET/POST API + ChangeAuditLog 联动）
    ✅ E2E 冒烟测试 35 项（A1-A10 审计项全覆盖，Batch 12）
    ✅ 日报自动化（cron_daily_report.sh → Telegram，UTC 0:00）
    ❌ 策略层标准 RSI/MACD/MA，无可证明的 alpha

  详细审核报告：docs/governance_dev/audits/2026-03-30--round2_cold_functional_audit.md
  修复计划：docs/governance_dev/2026-03-30--round2_fix_plan_batches_7_12.md

★ Phase 0 Cowork Round 2.5 审计（2026-03-31 · 3-agent 并行审计）：
  P0 修复：MessageBus.subscribe() 3→2 参数 bug（AnalystAgent 静默失败）
  P0 修复：layer2_engine "not worth" 文本解析 bug（"worth" 子串匹配，新增否定模式排除）
  P1 修复：3 个 Ollama 测试（大小写不符 + 错误消息 + 逻辑修复）
  清理：6 处 except-swallowing（governance_hub / pipeline_bridge / risk_routes 添加日志）
  287 条治理规格 Gap 分析：76% 已实施（67A + 18B + 8C + 2D）
  关键缺失：H0 Gate（DOC-02 指定 <1ms 确定性门控）· 回测引擎 · L3-L5 学习
  4-Phase 开发路线图已制定（详见 §11）
  详细报告：docs/governance_dev/audits/2026-03-31--gap_analysis_287_specs.md

★★★ 7-Agent 全系统审计（2026-03-31 · E3/E4/E5/CC/A3 + PM/PA 交叉复验）：
  规模：71 测试文件 / 2,480 测试用例 / 53 app 模块 / 全 HTML/JS/CSS
  发现：71 项问题（去重）· P0: 8 / P1: 18 / P2: 29 / P3: 16 · 预估 ~110 小时工作量

  4 个 PA 确认属实的 CRITICAL 问题（⚠️ 已全部修復）：
    ✅ CRITICAL-1：/openclaw/{path} 反向代理添加認證（main.py，asyncio.to_thread + Auth header）
    ✅ CRITICAL-2：_require_operator_role() isinstance 类型错误已修復
                   → AuthenticatedActor dataclass 正確類型檢查，所有治理端點恢復可用
    ✅ CRITICAL-3：GovernanceHub=None 時 submit_order() fail-closed 已修復
    ✅ CRITICAL-4：Guardian=None 時 pipeline_bridge.py fail-closed 已修復

  其他重要发现：
    ✅ pipeline_bridge.py 測試覆蓋已補強（65 測試 + 17 並發測試）
    ✅ governance_routes.py 測試覆蓋已補強（107 測試，10%→45%）
    ✅ set_analyst_agent 重複定義已合併
    ✅ 同步 urllib.request.urlopen 已改 asyncio.to_thread
    ✅ layer2_engine "not worth" 修復（詞邊界正則，排除 "know" 等誤判）
    ✅ 登录端点速率限制已改 5次/分钟 + IP 锁定
    ✅ SQL 查询全面参数化 · Token 恒定时间比较 · 无硬编码密鑰 · .gitignore 保护完整
    ✅ GovernanceHub fail-closed 核心设计依然一流（FROZEN 模式直接拒绝）

  GUI 可用性评估（A3，6.2/10）：
    ⚠ 界面是工程师视角设计，非操作员视角（SM-01/SM-02/Decision Lease 等术语直接暴露）
    ⚠ 学习系统 Tab 英文化严重（6 个核心指标全英文）
    ✅ 双层解释系统（ocExplain）/ 确认弹窗 / 实盘锁定前置条件 / 颜色系统 — 保留

  合规度（CC，B 级）：11/16 原则完全合规，4/16 部分合规，1/16 未实施
  安全评级（Wave 4 Sprint 4a-4e 後）：0 CRITICAL / 0 HIGH / 2 MEDIUM / 3 LOW（已知安全問題清零）

★ Wave 5a Position Sizing 重構（2026-03-31）：
  ✅ risk_per_trade_pct 2%→3%（每筆最大虧損 = 總額 3%）
  ✅ max_symbols 10→25（最多同時部署 25 個幣種）
  ✅ 動態 qty：每次下單時根據當前餘額重算（不再啟動時鎖死）
  ✅ 智能資本再分配：槽位滿時評估持倉保留價值，關閉弱倉投入高分新機會
  ✅ sizing 公式改為 risk/stop 反推名義金額，不除以 active symbol 數

★ Wave 5b Paper/Demo 同步修復（2026-03-31）：
  ✅ CRITICAL-1：_check_stops() 止損同步平 Demo 倉位（reduce_only）
  ✅ CRITICAL-2：Demo 下單失敗從 debug→WARNING + "DIVERGED" 明確標記 + stats 追蹤
  ✅ CRITICAL-3：governance_hub.reconcile() 參數名 demo_state→remote_state + dataclass→dict
  ✅ MOD-4：round_qty_for_exchange() 共用函數，Paper/Demo 收到完全相同 qty
  ✅ MOD-5：_on_position_open() 用 actual_qty（rounded），條件止損單 qty 與 Demo 一致
  ✅ 對賬引擎首次真正運行（之前因 TypeError 從未成功）

★ Wave 5 Sprint 0 BLOCKER 修復（2026-03-31 · commit d57ed05）：
  ✅ G-05：executor_agent.py 插入 acquire_lease()（原則 3 硬違反修復），fail-closed，6 個 Decision Lease 測試
  ✅ G-01：DEFAULT_DAILY_HARD_CAP_USD 15.0→2.0（DOC-08 §4），tab-ai.html 同步，2561 tests

★ Wave 5 Sprint 5a H1-H5 核心接通（2026-03-31 · commit ccdff73）：
  ✅ 5a-1：Scout→Strategist bus.send 鏈路端到端驗證（intel_received stats 可觀察）
  ✅ 5a-2：H0 Gate warn-only → blocking（`continue` fail-closed + intents_h0_blocked 計數器）
  ✅ 5a-3：H1 ThoughtGate MVP（budget/complexity/cooldown 三條同步規則，失敗→heuristic_evaluate）
  ✅ 5a-4：Strategist shadow=False 正式切換（前置條件 G-05+H0 blocking+Guardian 確認）
  ✅ 5a-5：H2 預算門控（Layer2CostTracker 注入 StrategistAgent）
  ✅ 5a-6：H3 ModelRouter（complexity<0.5→l1_9b / 0.5-0.8→l1_27b / ≥0.8→l2，L2 daemon thread）
  2879 tests passed

★ Wave 5 Sprint 5b Agent 落地完善（2026-03-31 · commit 9478c00）：
  ✅ 5b-1：H4 AI 輸出驗證（_validate_ai_output confidence∈[0,1]，fail-closed → heuristic）
  ✅ 5b-2/6：H5 CostLogger（record_ollama_call + roi_basis:"paper_simulation_only" 雙端 marker）
  ✅ 5b-3：apply_ai_consultation() DEPRECATED（warnings.warn + deprecation_notice 字段，向後兼容）
  ✅ 5b-4：ScoutWorker daemon 線程（30min 週期，1s interruptible sleep，start() 冪等）
  ✅ 5b-5：原則 14 集成測試（6 個 P14 tests，Mock Ollama crash → L0 fallback → 交易鏈路不中斷）
  2610 tests passed（+54 新測試）

  报告文件：docs/audit/March31/（7 份，详见 §十二参考文档指针）
  PM 工作计划：docs/audit/March31/PM_review_2026-03-31.md（P0-P3 批次 + 依赖图）
  PA 技术复验：docs/audit/March31/PA_review_2026-03-31.md（架构层补充 6 项）

★ P0 修復完成（2026-03-31 · 5 E1 並行 · E2+E4 通過）：
  ✅ governance_routes.py：_require_operator_role isinstance 修復（+15處屬性訪問），164 tests
  ✅ pipeline_bridge.py：Guardian=None fail-closed else 分支 + 重複方法合併
  ✅ paper_trading_engine.py：GovernanceHub=None fail-closed，7 測試文件補 mock hub，2224 tests
  ✅ main.py + GUI 靜態文件：openclaw_proxy 認證 + asyncio.to_thread + Authorization header
  ✅ layer2_engine.py：negation 詞邊界正則 + intent.reason getattr 安全訪問

★ Wave 0 P1 修復完成（2026-03-31 · 與 P0 並行 · E2+E4 通過）：
  ✅ P1-11：ollama_client max_retries = 0（CLAUDE.md 硬邊界對齊）
  ✅ P1-15：layer2_tools subprocess -- 分隔符 + 截斷 + 剝離
  ✅ P1-14：Shell 腳本日誌路徑 /tmp/ → 項目目錄 logs/restart.log（防符號鏈接攻擊）
  ✅ P1-12：auth_login 憑證讀取從每請求文件 I/O 改為啟動緩存
  ✅ P1-5：governance_routes _sanitize_log() helper + 7 處日誌注入點修復

★ Wave 1 修復完成（2026-03-31 · E2+E4 通過）：
  ✅ PA-4.3：governance_routes.py DI 統一（_current_actor helper + 26 處 Depends(current_actor)）
  ✅ HTTPException 穿透：approve/reject audit change except HTTPException: raise 防止吞異常

★ Wave 2 修復完成（2026-03-31 · E2+E4 通過）：
  ✅ P0-8：main_legacy.py _COMPILE_STATE_SIG_CACHE（id(fn) 鍵值，避免每次 inspect.signature）
  ✅ P1-1：auth_login 速率限制 5次/分 + _login_fail_counts + IP 鎖定 15 分鐘（5 次失敗後）
  ✅ P1-13：trading.html 7 處 innerHTML XSS → ocEsc() 包裝
  ✅ P1-2：governance_hub OPENCLAW_GOVERNANCE_ENABLED env var 移除（治理不可通過環境變量禁用）
  ✅ P1-6：pipeline_bridge 65 測試（program_code/local_model_tools/tests/）
  ✅ P1-8：ws_listener 50 測試（reconnect / on_close / on_error 全覆蓋）
  ✅ P1-9：demo_connector 41 HMAC _sign() 測試
  ✅ P1-18：pipeline_bridge 並發死鎖分析 + 17 測試（confirmed no real deadlock：on_tick 先釋放鎖再調用 downstream）

  兩次 commit：ec0e794（16 files · P0+Wave0-2 第一批）· c113ab2（10 files · paper_engine + pipeline_bridge）

★ Wave 3a P0 修復完成（2026-03-31 · E2+E4 通過 · commit c6a8845）：
  ✅ P0-NEW-1：governance_routes /reconcile 缺少 Operator 角色驗證 + except HTTPException 穿透
  ✅ P0-NEW-2：logger 參數順序確認正確（無需改動）
  ✅ P0-NEW-3：27 處 detail=str(e) → "Internal server error"（防 Python 異常路徑洩漏）

★ Wave 3b P1 修復完成（2026-03-31 · E2+E4 通過 · commit 2eda4ec）：
  ✅ P1-NEW-1：openclaw_proxy 過濾 Authorization header（用戶 Token 不透傳 Gateway）
  ✅ P1-NEW-2：_COMPILE_STATE_SIG_CACHE id(fn) → weakref.WeakKeyDictionary（防 GC id 重用誤判）
  ✅ P1-NEW-3：_login_fail_counts 加 asyncio.Lock + 2000 IP 容量上限（防並發競態 + OOM）
  ✅ P1-NEW-4：auth_login token 來源統一為 settings.api_token（消除磁盤重讀）
  ✅ P1-NEW-5：openclaw_proxy 異常補 logger.warning（不洩漏細節）
  ✅ P1-NEW-6：OPENCLAW_GATEWAY_HOST 改模組頂層緩存 _OC_HOST
  ✅ P1-NEW-7：layer2_engine._session_lock threading.Lock → asyncio.Lock

★ Wave 3c P1 修復完成（2026-03-31 · E2+E4 通過 · commit bf75254）：
  ✅ P1-4：governance_hub.acquire_lease() 補傳 expires_at_ms（TTL 原從未生效）+ TOCTOU 保護
  ✅ P1-10：test_pipeline_bridge 補 TestPipelineBridgePerceptionPlane（3 測試確認 register_data 調用）
  ✅ P1-17：governance_hub.is_authorized() 鎖外讀取修復（先賦局部變量防 None unpack，E3-M5）

★ P1-16 H0 Gate Day 1 完成（feature/p1-16-h0-gate-deterministic · commit 3ccd982）：
  ✅ app/h0_gate.py（651 行）：5 個確定性 check（freshness/health/eligibility/risk/cooldown）
  ✅ tests/test_h0_gate.py（37 個測試）：SLA 驗證通過（實測 <5μs，SLA 要求 <1ms）

★ P1-16 H0 Gate Day 2 完成（feature/p1-16-h0-gate-deterministic · commit 5d53619）：
  ✅ H0HealthWorker：背景 psutil 採樣線程（daemon + 可中斷睡眠 + db_probe_fn 可注入）
  ✅ tests/test_h0_gate.py（40 個新測試）：health×12 / risk×12 / cooldown×8 / SLA timeit×2 / worker×6
  ✅ 1000 次 timeit SLA 壓測 blocked + allowed 路徑均 < 1ms avg（實測 <0.5ms avg）

★ P1-16 H0 Gate Day 3 完成（feature/p1-16-h0-gate-deterministic · commit 2ed20f0）：
  ✅ paper_trading_routes.py：H0Gate singleton + H0HealthWorker daemon 啟動（ImportError fallback H0_GATE=None）
  ✅ pipeline_bridge.py：set_h0_gate() + on_tick() price_ts 更新 + _process_pending_intents() warn-only 前置門
  ✅ governance_routes.py：GET /governance/h0-gate/status 只讀端點（HTTPException 穿透，固定 detail 字符串）
  ✅ risk_manager.py：set_h0_gate() + cooldown 事件 push to H0Gate.update_risk()
  ✅ phase2_strategy_routes.py：H0Gate 注入 PipelineBridge + RiskManager（lazy import，None 守衛）
  ✅ test_h0_gate.py：18 個集成測試（77→94）：pipeline/routes/risk × warn-only/503/push 全覆蓋
  ✅ 2539 passed / 17 pre-existing failed（新增 17 tests，超過 PM 要求 2530）

★ GUI + Ollama 优化（2026-03-31 Session）：
  GUI：Paper+Demo 合并为「测试交易」子 Tab（iframe 包装器），新增「实盘交易」锁定占位 Tab（tab-live.html）
  GUI：11 Tab 重排（系统→实盘锁→测试→K线→策略→风控→AI→学习→治理→监控→设置）
  GUI：子 Tab 样式修复（半椭圆→下划线，与外层 Tab 栏风格一致）
  GUI：设置 Tab Modal CSS 补全（修复「计划重启」对话框常驻 bug）
  GUI：Paper/Demo 布局对齐（账户余额卡片在上，盈亏概览在下）
  Ollama：think=False 参数修复（必须放 JSON 顶层，非 options 内）→ 9B 8.7s→1.9s，27B 21s→9.9s
  Ollama：模型分配（9B 快速路径；27B 复杂/周报；DEFAULT_MODEL 改 9B）
  Ollama：get_ollama_client_27b() 27B 单例，AnalystAgent 改用 27B，analyze_patterns 加 think=True
  L1 Edge Filter：set_ollama_client() 修复（原为死代码，从未注入，现在 pipeline_bridge 正常接入）
  后台市场流：MarketDataDispatcher 改为服务启动即运行（常驻），不依赖 Paper/Demo 会话状态
  周报：扩展为周三简报（27B Ollama）+ 周日详报（Claude L2），独立去重键
  工程日志：docs/worklogs/control_api_gui/2026-03-31--gui_tab_restructure_ollama_optimization.md

历史 Batch 3-12 + Session 8-12 + Phase 3 详细记录已归档至：
  → docs/worklogs/control_api_gui/2026-03-31--round2_batch_records_archive.md

Scanner 规则（最新）：
  MA Crossover 部署过滤   = 24h涨跌幅 > 40% 跳过
  MA Crossover 置信度     = 0.55（扫描器部署）/ 0.50（默认 BTCUSDT）
  Trend 评分上限          = 100（原无限制，防止压制 funding_arb/grid）
  Unknown regime 入场     = 禁止（新上线品种冷启动保护）
  Market Feed 自动重启    = ✅（服务 restart 后自动恢复，无需手动）

Runtime 硬状态：
  system_mode             = demo_only          # Operator 授權 2026-03-31
  execution_state         = disabled           # 不可改（live 前必須保持）
  execution_authority     = not_granted        # 不可改（live 前必須保持）
  decision_lease_emitted  = false              # 不可改
  live_execution_allowed  = false              # 不可改（live 防護硬邊界）
```

---

## 四、章节树

```
A-C  基础层 / OpenClaw 模型层 / 接入前治理      ✅ 完成
D    Readonly Observer 主链                     ✅ 完成
E    Business Event Classification              ✅ 完成
F    Event-Driven Transition Scaffold           ✅ 完成
G    真实业务事件验证层                          ✅ 收口
H0   Local Deterministic Judgment Core          ✅ 完成
H1-H5 AI 治理层                                ✅ 完成
     Phase 2 治理模組 T2.01–T2.23               ✅ 完成（21 模组 + PM/TW 双审核通过）
     Phase 3 GovernanceHub 集成                  ✅ 完成（Hub+8路由+4SM接入+安全审核+46测试）
I1-I10 Decision Lease shadow control plane      ✅ 完成（shadow-only）
J    Transition Engine Skeleton                 ✅ shadow-only closeout
K    Paper / Demo Gate                          ✅ design-only gate closed
     Control API v1                             ✅ 104 路由，安全加固完成
     GUI Operator Console v1                    ✅ Learning Cockpit + Net PnL + Paper Trading + 统一控制台
L    Learning / Self-Observability / Net PnL    ✅ 全部完成
     Paper Trading Engine Beta                  ✅ 24 路由 + 影子决策 + 性能指标
     Layer 2 AI 推理引擎                        ✅ 5 模块 + 9 路由 + 79 测试
     全品类风控框架                              ✅ 4 轮审核（P0/P1/P2 + 对抗性止损 + AI 注意力税）
     Phase 2 本地策略工具包                      ✅ 严格审核（K线+6指标+信号+4策略+编排器+11路由）
     Phase 3 管线桥接+止损+信号增强              ✅ 完成（管线接通+StopManager+Regime检测+3新规则+历史K线引导）
     全系统审核 A-K 修复                         ✅ 完成（7C+19H+28M+16L 全修 + 路径统一 + I章去重 + mutator 3x→1x）
     GUI 三层架构                                ✅ 完成（Grafana 监控 + TradingView K线 + Bybit Demo 双重执行 + 登录系统）
     GUI 10-Tab 专业控制台                       ✅ 完成（10 Tab + common.js + 双层解释 + 三层信息密度）
     自主交易 Agent                              ✅ 完成（市场扫描器 650 符号 + 策略自动部署 + 多币种支持）
M    Supervised Live Gate                       ⬜ 未开始
N    Constrained Autonomous Live                ⬜ 未开始
```

**⚠️ 任何章节"完成"都不等于 live 放权。执行权限仍未授予。**

---

## 五、架构总览

```
[数据与观察层]           Bybit REST + WS → Postgres + Observer
[H0 本地判断内核]        freshness / health / eligibility / risk envelope
[GovernanceHub]          ★ SM-01授权 + SM-04风控 + SM-02租约 + EX-04对账（跨SM级联）
[H1-H5 AI 治理层]       thought_gate / budget / model_router / governor / cost_logging
[I Decision Lease]       GovernanceHub.acquire_lease() / release_lease()
[Control API v1]         FastAPI 121+ 路由（含 /governance 8 端点）
[GUI + Learning]         Operator Console + Learning Cockpit + Paper Trading Dashboard
[Paper Trading Engine]   7 状态生命周期 / 成交模拟 / PnL / 治理 gate 接入
[Layer 2 AI 推理]        L0 确定性 → L1 Haiku → L2 Sonnet/Opus + 4 层搜索降级
[风控框架]               P0/P1/P2 三层 + 对抗性止损 + AI 注意力税
[Phase 2 策略]           KlineManager → IndicatorEngine → SignalEngine → 4 策略 → Orchestrator
[管线桥接]               PipelineBridge: Tick Fan-Out + Intent→Order + 治理 gate + 执行回调
[止损管理器]             StopManager: Hard/Trailing/Time Stop + ATR 动态仓位
```

**详细架构 + 各层子模块说明见：** `docs/references/2026-03-27--system_reference_handbook.md`

---

## 六、硬边界（永远不能违背）

```python
system_mode             = "demo_only"      # Operator 授權 2026-03-31（Paper + Bybit Demo only）
execution_state         = "disabled"       # 不可改（live 前必須保持）
execution_authority     = "not_granted"    # 不可改（live 前必須保持）
decision_lease_emitted  = False            # 不可改
max_retries             = 0                # 不可改

# 硬错误：
# - should_call_ai=true 但 invocation 没发生
# - Bybit API timeout / retCode != 0
# - execution authority 意外被授予
# - 伪造 AI 调用或交易活动
# - 自动改 live 配置 / 自动放开 execution authority
```

---

## 七、重要技术记录

### Legal no-call 语义
```python
route_plan = route_skip, should_call_ai = false
# → 合法 observation terminal path，不是失败
```

### Legal idle account 语义
```python
position_count = 0, order_count = 0
# → info/idle，不是 blocker
```

### Authoritative checkers
```bash
# H 链
helper_scripts/maintenance_scripts/bybit_connector/run_i10_canonical_h_chain_recheck.sh
# I 链
helper_scripts/maintenance_scripts/bybit_connector/run_i10_canonical_decision_lease_recheck.sh
```

### 已知文件名修正
| 旧名 | 当前正确名 |
|---|---|
| `bybit_local_risk_envelope_builder.py` | `bybit_local_risk_envelope_gate.py` |
| `bybit_local_trade_eligibility_handoff.py` | `bybit_local_trade_eligibility_handoff_builder.py` |
| `bybit_local_judgment_contract_check.py` | `bybit_local_judgment_final_audit_contract_check.py` |

---

## 八、GitHub 与本地路径

```
GitHub repo:    yunancun/BybitOpenClaw
本地主工作树:   /home/ncyu/BybitOpenClaw/srv
                /home/ncyu/srv  ← symlink

本地-only（不进 Git）：
  settings/          真实 env / secrets
  trading_services/  .env / runtime / connector_logs / decision_packets
```

**工作流：GitHub-first** — 已 push 代码从 GitHub 读，runtime/latest 等本地-only 才用 shell

---

## 九、启动检查

```bash
git status && git log --oneline -5
bash helper_scripts/maintenance_scripts/bybit_connector/run_i10_canonical_h_chain_recheck.sh
bash helper_scripts/maintenance_scripts/bybit_connector/run_i10_canonical_decision_lease_recheck.sh
python3 scripts/bybit_observer_acceptance_check.py
python3 scripts/bybit_runtime_state_resolver.py
```

### ★ TODO.md 強制規則（每次 Claude 接手必須遵守）

**接手時（會話開始）：**
- 必須讀取 `/home/ncyu/BybitOpenClaw/srv/TODO.md` 確認當前工作狀態
- 從 TODO.md 中找到第一個 `[ ]` 未完成項目，作為本次會話起點
- 若用戶有明確指令，以用戶指令為準，但仍需先讀 TODO.md 了解上下文

**發現新問題時（任意時刻）：**
- 審計報告（E3/E5/FA/PA/PM）產出新問題 → 立即追加到 TODO.md 對應的 Wave/批次區塊
- 格式：`### [ ] 問題編號：簡短描述` + 檔案/行號/修復方案/工時/E1 指派
- 不能等到會話結束才批量更新，發現即寫入

**修復完成後（E2+E4 通過，PM/PA/FA 確認後）：**
- 將對應條目的 `[ ]` 改為 `[x]`，**不得刪除條目**
- 在條目末尾追加一行：`- ✅ 完成：commit XXXXXXX（YYYY-MM-DD）`
- 更新 TODO.md 頂部「當前測試基準線」的 passed 數字
- commit 時帶上 TODO.md（與生產代碼改動一起 commit）

---

## 十、代码与文档规范

### 雙語注釋規範（強制，E1/E1a 寫代碼必須遵守，E2 審查必查）

每個新建或修改的函數、類、模塊，必須包含中英對照注釋，供 Operator 和維護者閱讀：

1. **模塊頂部 `MODULE_NOTE`**：中英雙語說明模塊用途、所屬層次、主要職責
2. **函數/方法 docstring**：中英兩段，說明「做什麼」和「為什麼這樣設計」
3. **關鍵邏輯 inline comment**：說明意圖，而非翻譯代碼本身
4. **fail-closed / fallback 路徑**：必須注釋說明為何選擇此 fallback 行為
5. **安全相關代碼**（認證/授權/XSS 防護）：必須注釋說明防護目的

> E2 Code Review 必查：缺少雙語注釋 → 打回 E1/E1a 重做，不計為通過。

### 大章節完成後強制同步（Sprint / Wave 結束時）

每個 Sprint 或 Wave 完成（E2+E4 通過、PM 確認）後，在 commit 前必須：

1. **更新 `CLAUDE.md`**：§三「當前系統狀態」+ §十三.4「當前任務狀態」+ §十四「一句話狀態」
2. **更新 GitHub `README.md`**：反映最新完成狀態、測試數、功能摘要
3. **一起 commit**：生產代碼 + TODO.md + CLAUDE.md + README.md 放同一個 commit

> 不允許先 commit 代碼、事後補文檔。文檔同步是 Sprint 完成的必要條件，不是可選項。

### 新脚本规范
1. 头部 `MODULE_NOTE`（中英双语）
2. 输出 `latest` + `dated` 两份文件
3. 补 `contract check`
4. 更新 `SCRIPT_INDEX.md`

### docs/ 文档规范
1. 文件放对应分类目录（`worklogs/` / `handoffs/` / `decisions/` / `references/`），禁止放 `docs/` 根
2. 命名：`YYYY-MM-DD--功能描述.md`
3. **每次新增必须更新 `docs/README.md` 底部索引**
4. 中文为主 + 英文辅助
5. 完整规范见 `docs/README.md`

---

## 十一、后续推进顺序（2026-03-31 Wave 0-2 完成後更新）

```
已完成摘要：
  ✅ A-L 全部章节 + 策略工具包 + 管线桥接 + 全系统审核
  ✅ GUI 三层架构 + 11-Tab 专业控制台（测试子Tab + 实盘锁）
  ✅ 自主交易 Agent（市场扫描器 650 符号 + 策略自动部署）
  ✅ Phase 2 治理模組 T2.01–T2.23（21 模组 · 1,522 测试）
  ✅ Phase 3 GovernanceHub 集成（4SM 接入 + 安全审核 9 项修复）
  ✅ Round 2 Batch 3-12 全部完成（5 Agent 接入 + OMS + PaperLiveGate + E2E）
  ✅ L1 本地推理（Ollama + Qwen 3.5）+ 0% 胜率四根因全修复
  ✅ Phase 0 Round 2.5 审计（2,227 tests · 2 P0 + 1 P1 修复 · 287-spec gap 分析）
  ✅ 7-Agent 全系统审计（E3/E4/E5/CC/A3/PM/PA · 71 项问题 · 4 CRITICAL 确认）
  ✅ Wave 0-2 全部完成（8 CRITICAL 修復 + 15 項 P1 + DI 統一 + 覆蓋率補強）

★★★ 當前工作重心：Wave 3 + P2/P3 批次

  【Wave 3 — P1 剩餘高難度項（每項 2-3 小時）】
    P1-4:  Decision Lease 閉環驗證（lease 超時 → 訂單自動失效）
    P1-10: Perception Plane register_data() 注入（零調用問題）
    P1-17: GovernanceHub TTL 競態修復（lease TTL 與 SM-01 授權 TTL 競態）
    P1-16: H0 Gate 確定性門控（DOC-02 · <1ms SLA · Live 前必須 · 預估 3 天）

  【P2 批次 — 下一版本（~80h · 29 項）】
    優先級：P2-6/P2-7/P2-8（風控覆蓋補強）
           P2-12/P2-15（pipeline_bridge 邊界用例）
           P2-25（GUI 術語友好化第一批）
    完整清單：docs/audit/March31/PM_review_2026-03-31.md

  【P3 批次 — 積壓（~36h · 16 項）】
    GUI 術語友好化（SM-01 等工程術語 → 中文操作員視角）
    性能優化（E5 報告 49 項中優先級最高的）

★★ 开发路线图 v2（287 条治理规格 Gap 分析 · Wave 0-2 修復後繼續）：

  Phase 1: 安全闸补全 + 稳定性（预估 5 天）
    ★ Batch 1A: H0 Gate 确定性门控（DOC-02 · <1ms SLA · Live 前必须）
    Batch 1B: Cooldown 联动 + M-of-N 签名验证 + 数据品质→风控降级
    前置条件：Wave 3 完成後開始

  Phase 2: 学习管线 + 回测（预估 10 天）
    Batch 2A: L2 模式发现自动化 + Truth Source Registry 形式化
    Batch 2B: 回测引擎 MVP（策略 alpha 验证基础设施）
    目标：系统能从交易历史自动学习 + 验证策略有效性

  Phase 3: 进化能力（预估 15 天）
    Batch 3A: L3 假设与实验管线 + L4 策略进化
    Batch 3B: 策略 Alpha 验证 + SM-04 延迟 SLA 压测
    目标：参数自动优化 + 新策略生成 + 压力测试

  Phase 4: Paper Trading 观察 + Live 准备（5 + 21 天）
    Paper Trading 稳定运行 21 天观察期
    Live 前置条件核验 + Supervised Live Gate
    ★ SM-01 授权 TTL 分级设计（与 Learning Tier 挂钩）：
      L1-L2（初期 live）  = 24h
      L3（稳定运行 30d+） = 72h
      L4（高胜率长期）    = 7d
      L5（完全成熟）      = 30d

待处理问题（已记录，非紧急）：
  - Learning Cockpit GUI 数据展示（依赖 Analyst 数据积累）
  - RiskManager daily loss 跨天不重置（已验证有重置逻辑，影响极小）

之后：
  M 章：Supervised Live Gate（需先积累 paper trading 数据）
  N 章：Constrained Autonomous Live

Live 前置条件（M/N 前必须核验）：
  - Paper Trading 稳定运行至少 21 天
  - H0 Gate 确定性门控已实施并验证
  - 风控框架实测验证 + 回测引擎验证策略 alpha
  - provider pricing table 正式绑定
  - authority grant contract + execution adapter contract
  - 远程访问安全方案（HTTPS + CSP）
```

---

## 十二、参考文档指针

以下内容已从 CLAUDE.md 移出到独立文件。需要时请读取对应文件。

### ★★★ 全系统审计报告（audit/March31/）— 修復已完成

| 文件 | 内容 |
|------|------|
| `docs/audit/March31/E3_security_audit_2026-03-31.md` | 安全审计：3 CRITICAL / 5 HIGH / 6 MEDIUM / 5 LOW（gate 绕过 · 注入 · 密钥泄漏） |
| `docs/audit/March31/CC_compliance_check_2026-03-31.md` | 合规检查：11/16 原则完全合规，B 级，1 硬违规，9 缺口 |
| `docs/audit/March31/E4_testing_report_2026-03-31.md` | 测试评估：71 文件/2480 用例，pipeline_bridge 15%，governance_routes 10%（已補強） |
| `docs/audit/March31/E5_optimization_report_2026-03-31.md` | 优化评估：49 项（3 Critical · 14 High · 22 Medium · 10 Low），含性能/重复/可读性 |
| `docs/audit/March31/A3_gui_usability_report_2026-03-31.md` | GUI 可用性：6.2/10，工程师视角设计，术语友好化建议 |
| `docs/audit/March31/PM_review_2026-03-31.md` | ★ PM 整合审核：71 项去重，P0-P3 批次计划，~110h 工时，依赖图 |
| `docs/audit/March31/PA_review_2026-03-31.md` | ★ PA 技术复验：4 CRITICAL 确认属实，1 误报，6 架构层补充问题 |

### 参考文档（references/）

| 内容 | 文件位置 |
|------|---------|
| **系统参考手册** | `docs/references/2026-03-27--system_reference_handbook.md` |
| 全品类风控框架设计 | `docs/references/2026-03-27--phase1_risk_framework_and_agent_autonomy_design.md` |
| Phase 2 严格审核报告（8C+15H+25M+19L） | `docs/references/2026-03-27--phase2_strict_audit_report.md` |
| Phase 2 修复路线图 | `docs/references/2026-03-27--phase2_audit_fix_roadmap.md` |
| Phase 2 第二轮审核报告（实战适用性） | `docs/references/2026-03-27--phase2_round2_strategic_audit_report.md` |
| 全系统 A-K 审核报告（7C+19H+28M+16L） | `docs/references/2026-03-27--full_system_audit_A_to_K.md` |
| Layer 2 AI 推理引擎实现计划 | `docs/references/2026-03-27--layer2_ai_reasoning_engine_implementation_plan.md` |
| 本地交易逻辑审查 + 策略补齐计划 | `docs/references/2026-03-27--local_trading_logic_audit_and_strategy_plan.md` |
| 远程访问指南（Tailscale + 安全配置） | `docs/references/2026-03-27--remote_access_guide.md` |

### 工作日志（worklogs/control_api_gui/）

| 内容 | 文件位置 |
|------|---------|
| ★ **Round 2 Batch 3-12 + Session 8-12 详细记录归档** | `docs/worklogs/control_api_gui/2026-03-31--round2_batch_records_archive.md` |
| GUI Tab 重构 + Ollama 优化工程日志 | `docs/worklogs/control_api_gui/2026-03-31--gui_tab_restructure_ollama_optimization.md` |
| ★★ Session 4 GUI 专业控制台（6 commits+17 files+3964 行+6 AI 供应商） | `docs/worklogs/control_api_gui/2026-03-27--session4_gui_10tab_professional_console.md` |
| ★ Session 6 胜率0%根因 + 4项修复 | `docs/worklogs/control_api_gui/2026-03-28--session6_halfday_data_analysis_and_fixes.md` |
| ★★ Session 7 系统全面审核 + 5项修复 | `docs/worklogs/control_api_gui/2026-03-28--session7_system_audit_and_fixes.md` |
| ★★★ Session 8 A-J 全面功能审核报告 | `docs/worklogs/control_api_gui/2026-03-28--session8_functional_audit_report.md` |

### 治理开发（governance_dev/）

| 内容 | 文件位置 |
|------|---------|
| **Phase 2 执行总览**（21 模组矩阵 + 关键指标） | `docs/governance_dev/phase2_execution/T2_EXECUTION_SUMMARY.md` |
| ★ **287-Spec Gap 分析（Phase 0 Round 2.5）** | `docs/governance_dev/audits/2026-03-31--gap_analysis_287_specs.md` |
| 287 条规格完整列表 | `docs/governance_dev/audits/2026-03-31--spec_requirements_287.md` |

---

## 十三、AI Agent 角色体系与强制工作链（默认协议）

> **强制规则：项目中所有任务（实现、审查、评估、文档）必须按角色分工派发，禁止 Claude 主会话身兼多职直接全部完成。**

### 13.1 15 个标准角色定义

#### 管理层（Planning & Governance）
| 代号 | 全称 | 职责范围 |
|------|------|---------|
| **PM** | Project Manager（项目经理） | 优先级整合、批次计划、风险管理、跨报告去重、最终验收 |
| **FA** | Functional Auditor（功能审计师） | 功能规格验证、Gap 分析、业务逻辑审查、Phase 任务书制定 |
| **PA** | Project Architect（项目架构师） | 技术复验、架构决策、可行性评估、任务派发设计、副作用识别 |

#### 质量保证层（Quality Assurance）
| 代号 | 全称 | 职责范围 |
|------|------|---------|
| **CC** | Compliance Checker（合规检查员） | 16 条根原则逐一验证、硬边界合规、代码规范合规 |
| **E2** | Code Reviewer（代码评审工程师） | PR 审查、代码可维护性、副作用识别、安全代码审查 |
| **E3** | Security Auditor（安全审计员） | 安全审计（gate 绕过/注入/密钥泄漏/认证授权/OWASP） |
| **E4** | Test Engineer（测试工程师） | 测试覆盖评估、测试设计、回归测试执行、边界/并发/异常用例 |
| **E5** | Optimization Engineer（优化工程师） | 代码精简/性能/可读性评估（不改功能） |

#### 执行层（Implementation）
| 代号 | 全称 | 职责范围 |
|------|------|---------|
| **E1** | Backend Developer（后端开发工程师） | Python / FastAPI 功能实现、bug 修复、核心逻辑 |
| **E1a** | Frontend Developer（前端开发工程师） | HTML / JS / CSS GUI 实现、API 集成、交互逻辑 |

#### 专项审查层（Specialist Review）
| 代号 | 全称 | 职责范围 |
|------|------|---------|
| **A3** | UX Auditor（用户体验审计员） | GUI 可用性、术语友好性、操作流程、反人类设计识别 |
| **R4** | Document Auditor（文档审计员） | 文档质量、交叉引用准确性、索引完整性 |
| **TW** | Technical Writer（技术写作员） | 双语注释质量、MODULE_NOTE 规范、工程日志写作 |

#### 分析层（Analysis）
| 代号 | 全称 | 职责范围 |
|------|------|---------|
| **AI-E** | AI Effectiveness Evaluator（AI 效果评估员） | AI 使用效果、成本/性能分析、模型分配评估、Ollama 优化 |
| **QA** | Quality Assurance（最终集成验收） | 端到端集成测试、上线前系统验收、跨模块一致性确认 |

---

### 13.2 强制工作链（交叉协作流程）

#### 默认第一步：PM + FA 双重确认（强制，所有任务启动前）

```
任何新 Batch / 新功能 / 新修复 → 必须先由 PM 和 FA 并行完成规划：

  PM 负责：                           FA 负责：
  - 优先级排序（P0/P1/P2/P3）          - 功能规格确认（要做什么）
  - 工时估算与批次分组                  - Gap 分析（缺什么）
  - 依赖关系识别                        - 验收标准定义
  - 风险评估                            - 与 16 条根原则对照

  PM + FA 双重确认输出 → PA 派发任务 → 并行执行
```

#### 标准全流程工作链

```
阶段 1【规划】（并行）
  PM: 优先级 + 批次计划 + 风险
  FA: 功能规格 + Gap 分析 + 验收标准
           ↓ PM+FA 双重确认
阶段 2【架构】（串行，PA 基于 PM/FA 输出）
  PA: 技术方案 + 任务派发（最大并行） + 副作用预判

阶段 3【执行】（最大并行）
  E1 (后端) ──┐
  E1a (前端) ─┤ 完全并行执行各自任务
  E1-x... ────┘（E1-Alpha/Beta/Gamma 等并行实例）

阶段 4【审查】（串行）
  E2: 代码审查（所有 E1/E1a 改动）

阶段 5【质量验证】（并行）
  E3: 安全验证 ─┐
  E4: 测试回归 ─┤ 并行执行
  E5: 优化扫描 ─┘

阶段 6【专项审查】（按需，并行）
  CC: 合规检查 ─┐
  A3: GUI 审查 ─┤ 仅在涉及对应领域时激活
  R4: 文档审查 ─┤
  TW: 注释审查 ─┘
  AI-E: AI 效果审计（每季度 / 重大 AI 变更后）

阶段 7【验收】（串行）
  QA: 端到端集成测试
  PM: 最终确认 + 更新 CLAUDE.md 状态

阶段 8【文档同步，強制，Sprint/Wave 完成的必要條件】（并行）
  TW: 工程日志 + 双语注释补全
  R4: 文档索引更新（docs/README.md）
  → 更新 CLAUDE.md（§三狀態 + §十三.4 + §十四一句話狀態）
  → 更新 GitHub README.md（最新功能、測試數、完成狀態）
  → 生產代碼 + TODO.md + CLAUDE.md + README.md 放同一個 commit
```

#### 纯修复任务快速通道（P0 紧急修复）

```
PA 读取问题报告 → 派发 E1 并行修复 → E2 review → E4 回归 → PM 确认
（跳过 FA / A3 / R4，但 E2 + E4 绝对不可跳过，任何情况均强制执行）
最大并行：5 个 E1 Agent 同时修不同文件
```

---

### 13.3 角色激活时机矩阵

| 任务类型 | 必须激活 | 可选激活 | 不需要 |
|---------|---------|---------|--------|
| P0 紧急安全修复 | PM · PA · E1 · E2 · E4 | E3 | FA · A3 · R4 · TW |
| 新功能实现 | PM · FA · PA · E1/E1a · E2 · E4 | CC · E3 · A3 | - |
| 全系统审计 | E3 · E4 · E5 · CC · A3 · PM · PA | FA · R4 · TW · AI-E | - |
| GUI 变更 | E1a · E2 · A3 | E4 · TW | E3（除非涉及安全） |
| 文档更新 | TW · R4 | PM | E1 · E2 · E3 |
| 合规复查 | CC · FA · PM | PA | E1 · E1a |
| 测试补充 | E4 · E2 | PA | E1（除非需要实现）|
| AI 优化 | AI-E · E1 · E2 | E5 | A3 · R4 |

---

### 13.4 当前任务状态（Wave 進度）

```
Wave 0：✅ P0（5 項）全部完成 + P1（5 項）全部完成（E2+E4 通過）
Wave 1：✅ PA-4.3 DI 統一（26 Depends）+ HTTPException 穿透（E2+E4 通過）
Wave 2：✅ P0-8/P1-1/P1-2/P1-6/P1-8/P1-9/P1-13/P1-18 全部完成（E2+E4 通過）
Wave 3a：✅ P0-NEW-1/2/3 全部完成（E2+E4 通過，commit c6a8845）
Wave 3b：✅ P1-NEW-1~7 全部完成（E2+E4 通過，commit 2eda4ec）
Wave 3c：✅ P1-4/P1-10/P1-17 完成（E2+E4 通過，commit bf75254）
P1-16：✅ Day 1+2+3 全部完成，已 merge（commit 03a5b29）
Wave 4 Sprint 4a：✅ P2-NEW-1/2/6（commit a2f4c70）
Wave 4 Sprint 4b：✅ P2-NEW-3/4 + P3-TECH-1/2/3（commit 6c80bc9）
Wave 4 Sprint 4c：✅ P2-NEW-7/8（commit 448f1e7）
Wave 4 Sprint 4d：✅ FA-2/3/4（commit 9cc134a）
Wave 4 Sprint 4e：✅ P2-NEW-9 + P2-NEW-5（commit 87c2651）
Wave 5a：✅ Position Sizing 重構 — 3% risk + 動態 qty + 智能資本再分配（commit 8223eb9）
Wave 5b：✅ Paper/Demo 同步修復 — 3 CRITICAL + 2 MODERATE（止損同步+失敗標記+對賬參數名+qty統一+條件單qty）
Wave 5 Sprint 0：✅ G-05 acquire_lease + G-01 AI daily cap $15→$2（commit d57ed05）
Wave 5 Sprint 5a：✅ H0 blocking + H1 ThoughtGate + shadow=False + H2/H3 ModelRouter（commit ccdff73）
Wave 5 Sprint 5b：✅ H4 validate_output + H5 record_ollama_call + ScoutWorker + P14 集成測試（commit 9478c00）

下一步：P3 批次（GUI 術語友好化，~36h）→ Phase 1 Batch 1B（Cooldown 聯動）

完整派发计划：docs/audit/March31/PA_review_2026-03-31.md（Part 2 任务派发）
```

---

### 13.5 Sub-Agent 啟動與完成強制協議（自動化記憶系統）

> **強制規則：每次用 Agent tool 喚起任何 sub-agent，必須在 prompt 中包含啟動序列。每次 sub-agent 完成任務，必須執行完成序列。兩端均不可省略。**

#### 啟動序列（每次 Agent tool prompt 的開頭必須包含）

```
你是 {角色代號}（{角色全名}）。在執行任何任務之前，必須先完成以下兩步：

【Step 1 - 讀取自身記憶】
讀取：docs/CCAgentWorkSpace/{角色代號}/memory.md
理解你目前的工作狀態、已知問題、歷史決策。

【Step 2 - 讀取最近上下文】
讀取：docs/CCAgentWorkSpace/{角色代號}/workspace/reports/ 目錄中最新的一份報告（按文件名日期排序最後一個）。
若目錄為空，跳過此步。

完成以上兩步後，再執行以下任務：
{實際任務內容}
```

#### 完成序列（每次 sub-agent 完成任務後必須執行）

```
任務完成後，必須執行以下兩步：

【Step A - 更新記憶】
更新 docs/CCAgentWorkSpace/{角色代號}/memory.md：
- 追加本次任務的關鍵發現、重要決策、需要記住的教訓
- 更新任何已過時的狀態信息
- 不要刪除歷史記錄，追加到文件末尾

【Step B - 存檔報告】
若本次任務產生了報告或分析輸出：
- 存至 docs/CCAgentWorkSpace/{角色代號}/workspace/reports/YYYY-MM-DD--描述.md
- 同時確認是否需要存一份到 docs/CCAgentWorkSpace/Operator/（僅限最終結論性報告）

若本次任務只是輔助性工作（如純代碼修復），跳過 Step B。
```

#### 角色代號 → workspace 路徑對照

| 代號 | workspace 路徑 | 代號 | workspace 路徑 |
|------|---------------|------|---------------|
| PM | `docs/CCAgentWorkSpace/PM/` | E2 | `docs/CCAgentWorkSpace/E2/` |
| FA | `docs/CCAgentWorkSpace/FA/` | E3 | `docs/CCAgentWorkSpace/E3/` |
| PA | `docs/CCAgentWorkSpace/PA/` | E4 | `docs/CCAgentWorkSpace/E4/` |
| CC | `docs/CCAgentWorkSpace/CC/` | E5 | `docs/CCAgentWorkSpace/E5/` |
| E1 | `docs/CCAgentWorkSpace/E1/` | A3 | `docs/CCAgentWorkSpace/A3/` |
| E1a | `docs/CCAgentWorkSpace/E1a/` | R4 | `docs/CCAgentWorkSpace/R4/` |
| QA | `docs/CCAgentWorkSpace/QA/` | TW | `docs/CCAgentWorkSpace/TW/` |
| AI-E | `docs/CCAgentWorkSpace/AI-E/` | | |

#### 記憶更新範圍說明

| 更新到 memory.md | 不需要更新 |
|----------------|-----------|
| 角色視角下的關鍵發現與教訓 | 可從代碼/git 直接查到的技術細節 |
| 重要決策及其原因 | 當前會話臨時上下文 |
| 與其他 Agent 的分歧或共識 | 已在報告文件中完整記錄的內容（報告存檔即可）|
| 需要在下次啟動時注意的風險點 | 無法在未來會話中復用的一次性信息 |

---

## 十四、一句话状态

> 截至 2026-03-31 Wave 5 多 Agent 正式落地 + H1-H5 接通全部完成：Sprint 0（G-05 acquire_lease + G-01 AI上限$2）→ Sprint 5a（H0 blocking + H1 ThoughtGate budget/complexity/cooldown + shadow=False + H2預算門控 + H3 ModelRouter）→ Sprint 5b（H4 validate_output + H5 record_ollama_call + ScoutWorker daemon 30min掃描 + 原則14集成測試）；2610 tests 通過；合規評級 B→A-（H1-H5 全接通）；系統 demo_only 模式；live_execution_allowed 仍為 false。
