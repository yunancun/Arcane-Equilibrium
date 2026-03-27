# 全系统审核报告（A-K 章节）
# Full System Audit Report (Chapters A-K)

**日期 / Date**: 2026-03-27
**审核范围 / Scope**: 569 文件 / 63,874 行代码 / A-K 全章节
**审核方法 / Method**: 5 个并行审核代理，3 个维度（代码正确性 / 板块交接 / 收益落地）
**状态 / Status**: 审核完成，待修复

---

## 总览

| 审核板块 | 文件数 | 行数 | CRITICAL | HIGH | MEDIUM | LOW |
|---------|--------|------|----------|------|--------|-----|
| D+E+F 基础层 | 98 | 12,667 | 0 | 3 | 6 | 4 |
| H0+H1-H5 AI 治理 | 75 | 13,536 | 2 | 4 | 6 | 4 |
| I 决策租约 + Control API | 64 | 9,944 | 2 | 4 | 6 | 4 |
| Paper Trading + Risk + L2 | 8 | 5,540 | 2 | 5 | 7 | 4 |
| 端到端集成 + 收益评估 | 全系统 | — | 1 | 3 | 3 | 0 |
| **合计** | **569** | **63,874** | **7** | **19** | **28** | **16** |

---

## CRITICAL（7 个）

### C1: Pipeline Bridge dict 迭代 crash
- **文件**: `pipeline_bridge.py:176`
- **问题**: `state.get("positions", [])` 实际是 dict，迭代得到 key (string)，`pos.get("symbol")` 必 crash
- **影响**: 有持仓时整个策略→Paper 流程崩溃

### C2: Market order 无 market_prices 时卡死
- **文件**: `paper_trading_engine.py:864`
- **问题**: 市价单提交时无价格则进入 WORKING 状态永不成交
- **影响**: 孤立订单永久堆积

### C3: resolve_provider_pricing 三重定义
- **文件**: `bybit_mainline_cleanup_helpers.py:183/227/481`
- **问题**: 最后一版（简陋版）胜出，精良版被覆盖，非 gpt-5-mini 模型 AI 成本全报 None
- **影响**: Net PnL 中 AI 成本不准确

### C4: H4 compute governor 拒绝 standard tier
- **文件**: `bybit_compute_governor_gate.py:81`
- **问题**: 只允许 "light" 和 "none"，standard 路径死亡
- **影响**: 中等复杂度 AI 调用永远被阻断

### C5: JsonStateStore.write() 非原子写
- **文件**: `main_legacy.py:1365`
- **问题**: `open("w")` 直接写，crash 即永久腐败（PaperStateStore 已正确用 tempfile+os.replace）
- **影响**: 控制状态文件不可恢复

### C6: JsonStateStore.read() 无 JSON 异常捕获
- **文件**: `main_legacy.py:1356`
- **问题**: 腐败文件导致全部 API 500 无恢复路径
- **影响**: 所有 API 请求全挂

### C7: 无启动自动化
- **文件**: 系统级
- **问题**: 服务器重启后 paper session / market feed / 策略全部丢失，无恢复脚本
- **影响**: 每次重启需人工干预

---

## HIGH（19 个）

### 基础层 D+E+F
1. Observer verdict builder `load_json` 无文件缺失保护 (`bybit_build_observer_verdict.py`)
2. 全系统 dated 文件无清理 — 30 天约 86,400 文件填满磁盘
3. `load_json` 返回类型不一致（None / {} / crash）跨章节

### AI 治理 H0+H1-H5
4. `bybit_ai_prompt_prep_builder.py` 双重 `load_json` 定义
5. `bybit_query_budget_gate.py` gate_state else 分支拼写错误 → 永远 pass_soft_warn
6. `normalize_recent_trade_fields(locals())` 传入 40 个局部变量深搜
7. 日累计 AI 预算无运行时检查

### I 章 + Control API
8. JsonStateStore.write() 非原子写（与 PaperStateStore 不一致）
9. 状态变更 TOCTOU — revision 检查在锁外
10. I 章 30+ 文件硬编码 `/home/ncyu/srv/` 路径
11. I 章 `consume_gate.py` / `preflight.py` 无 JSON 异常捕获

### Paper Trading + Risk + L2
12. Bridge market_prices 从 positions 提取但缺新 symbol 价格
13. Risk Manager 无 market_prices 时用 entry_price → 敞口过时
14. Pending market order price=None → exposure 算 0 → 风控绕过
15. L2 Opus 升级用旧 remaining 预算 → 可超日限
16. L2 API 调用无 timeout → hang 锁死线程

### 端到端
17. Observer cycle 是手动批处理 → H 链数据全靠人工触发
18. FundingRate_Arb 无数据源 → 策略完全不工作
19. Grid 默认价格 80K-100K 硬编码 → 超出范围零交易

---

## MEDIUM（28 个，摘要）

**D/E/F**: observer cycle overall_ok 不检查 post-guard；timestamp fallback now()；SHA1 指纹；G4.7 残留编号；transition 输入无异常保护；observer 各步返回类型混乱

**H**: report_ok 硬编码 True；H0 硬编码路径 vs H1 path_policy；cleanup_helpers 大量死代码；env var 无范围校验；output 无 chmod 0o600；max_retries 传递但未强制

**I/API**: 静态 HTML 路由无认证；deep_set 无 KeyError 保护；SHA-1 指纹；mutator 三重写入浪费；I 章工具函数到处复制粘贴；headroom 计算 missing=0

**Paper/L2**: float remaining_qty 残留；无 order TTL；PriceHistoryTracker 无上限；local vs UTC 日边界；L2 cost tracker 非原子写；bridge intents_filled 命名误导

**端到端**: console 401 刷屏；策略状态不持久化；无执行反馈到策略

---

## LOW（16 个，摘要）

硬编码 /home/ncyu 路径（D 章）；wallet coin 冗余提取；load_json 无 JSON 异常捕获（D 章多数文件）；F 章 state machine 只做分类不做状态转换（by design）；trailing blank line；load_json 重复定义 7+ 文件；budget gate 与 cost log 风格不一致；prompt injection 表面极小；http_status 永远 None；I 章 lease hard_disqualifiers 为字符串；I 章 dated 文件无清理；snapshot_id SHA-1 12 位；idempotency cleanup O(n log n)；approval bridge None 过滤；order/fill trim 不一致；MD5 用于止损 seed

---

## 板块交接评估

| 交接点 | 状态 | 说明 |
|--------|------|------|
| E → D | ✅ | 平行管线，文件合流 |
| D → H0 | ✅ | 字段名匹配 |
| H0 → H1 | ✅ | input builder 正确读取 |
| H1 → H2-H5 | ⚠️ | H4 阻断 standard tier (C4) |
| H5 → I | ✅ | lease schema 正确消费 |
| I → 未来 M 章 | ⚠️ | hard_disqualifiers 非可执行 |
| 策略 → Paper Trading | ⚠️ | Bridge crash bug (C1) |
| Observer → 实时管线 | ❌ | 完全断开 |

---

## 收益落地评估

### 最低可行启动路径

1. 修 C1（Bridge dict bug）— 10 分钟
2. 修 C2（市价单无价格 reject）— 10 分钟
3. 创建启动脚本 — 30 分钟
4. 调 Grid 参数到当前价格 — 5 分钟
5. 自动调用 bootstrap_from_rest — 10 分钟
→ Grid Trading 开始产生 paper 交易，1 小时后 MA + BB 出信号

### 修复优先级

**立即修（阻断运行）**: C1, C2, C7
**短期修（安全运行）**: C5, C6, H2, H19, bootstrap 自动调用
**中期修（提升收益）**: C3, C4, H18, Observer 自动化
