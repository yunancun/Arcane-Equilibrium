# program_code

玄衡 · Arcane Equilibrium 的 Python 侧源代码（控制平面 / GUI 后端 / 桥接 / 冷路径
学习与 5-Agent host）。交易 / 风控 / 策略配置 / 执行权威在 Rust `openclaw_engine`，
不在此目录（边界见 `../CLAUDE.md` §一）。

## 现有子目录（按 LOC 量级）

- `exchange_connectors/`：Bybit connector + FastAPI `control_api_v1`（控制平面 / GUI /
  桥接 / replay 表面 / governance 协调）。本目录的主体。
- `ml_training/`：ML / DL 训练管线（Teacher-Student + LightGBM + Optuna），冷路径。
- `learning_engine/`：学习管线五级 funnel（Observation→Lesson→Hypothesis→Experiment→Verdict），冷路径。
- `ai_agents/`：H1-H5 AI 治理层 / 本地 5-Agent（Scout/Strategist/Guardian/Analyst/Executor）冷路径 host。
- `local_model_tools/`：策略工具包 **stub-shim**——计算逻辑已收编到 Rust（DEDUP-PY-RUST），
  此处仅保留 import 表面，返回零值 / 委派 IPC，由 `tests/test_stub_contracts.py` 锁定契约。
- `market_data_processor/`：市场数据清洗 / 加工。
- `audit/`：审计工具脚本。
- `settings/`：**运行时数据目录**（gitignored 的 experiment_ledger / truth_registry snapshot），非代码。

## 已迁移到 Rust（Python 目录已删除）

旧 `governance/`（Phase 2 治理状态机）、`risk_control/`（H0 本地判断）、
`trade_executor/`（Decision Lease）的逻辑已收编进 Rust `openclaw_core`
（`governance_core.rs` · `h0_gate.rs` · `sm/risk_gov.rs`）。Python 侧仅保留控制平面
协调对象（如 GovernanceHub）与唯读投影，不再持有交易真相。

## 约定

此目录只放代码，不放大型数据文件、数据库导出（DB dump 归 `../backup_files/` 或 NAS）或日志。
