---
name: project_2026_06_01_rust_python_boundary_simplification_audit
description: 全程序通盤審計 — Rust/Python 邊界乾淨 0 誤置 + 精簡空間=少數熱點非膨脹；附 actionables
metadata: 
  node_type: memory
  type: project
  originSessionId: 32c26ae5-1871-403c-899e-a88e33e2f8de
---

2026-06-01 operator 要求通盤分析全程序兩問題：(1) Rust 化後有無把該 Rust 的誤寫成 Python (2) 精簡優化空間。主會話派 PA(權威邊界)/FA(跨語言重複死碼)/E5(精簡膨脹) 三獨立 agent 並行，結論互相印證。

**Q1 邊界：0 真正誤置（HIGH conf）。** 名字嚇人的 Python 檔(`h0_gate.py`/`risk_governor_state_machine.py`/`bybit_rest_client.py`/`guardian_agent.py`/`executor_agent.py`…) 全部 0 個 Rust 熱路徑 caller → 結構上不可能是交易真相層。歸三類：(A) 合法 Python 設計(GovernanceHub 協調/5-Agent 冷路徑/唯讀投影/parse→IPC→format)、(C) 遷移後死碼(`risk_manager.py` 52行shim、`h0_gate.py` gating 半部、Python `bybit_rest_client.py` 下單方法；Rust `h0_gate.rs` 註釋自證「移植自 Python 832行」)、(B) 誤置=**無**。**方法論**：PA 指出只靠檔名+docstring 會誤報 6-8 個(因 Python 檔註釋真寫 "hot path/<1ms SLA")，靠 call-path grep 推翻 → 命中 [[project_2026_06_01_fail_closed_gate_stack_root_cause]] 的「代碼審計易過度歸因」教訓。

**Q1 place_order — 2026-06-01 PA+CC 設計階段更正前述「0 caller」結論(FALSE NEGATIVE)**：`bybit_rest_client.py:801` Python `place_order()` 實有 **2 個生產 caller**=`helper_scripts/clean_restart_flatten.py:137/:178`(reduce-only demo flatten + dust sweep)，經 `clean_restart.sh:271` + `fresh_start.sh:252` 兩個生產生命週期腳本調用。先前 FA/PA grep 只掃 `program_code/` 漏掉 `helper_scripts/` 的 caller。關鍵：此路徑**設計用於引擎停止時**用 REST 平倉(IPC 此時不可用)，Rust 無替代。mainnet 已硬禁(`return 7`)→demo-only，**無 hard-boundary 違規但是真實能力**，直接刪會破壞兩腳本。CC BLOCKER-1：刪除式 diff 必 REJECT。operator 原指示「移除」基於 0-caller 假前提 → 已 push back，建議 **B-1 保留+加固**(client 層加 mainnet fail-closed 斷言)。**教訓:再次命中「grep 範圍不全 → 假死碼」,刪碼前 helper_scripts/ + 動態 caller 必掃**。

**Q1 策略性債**：SM-01/02/04(Auth/Lease/RiskGov) **雙源**(Python `risk_governor_state_machine.py` ↔ Rust `sm/risk_gov.rs` 等)。非誤置(契約允許控制平面 Python + 引擎 Rust 鏡像)，但是手動同步 silent drift 隱患 → 待 operator 決定：接受/加跨語言契約測試/長期單源收斂。

**Q2 精簡：精瘦+少數熱點，非膨脹(E5，FA 印證)。** 全庫只 1 檔破 2000 硬上限(`strategy_ai_routes.py` 2552)，Rust 0 超標。投機性死碼疑點(pipeline slots/v5.8 凍結 stub/dream/cognitive/opportunity) 查證全 load-bearing 有 caller。Rust 大檔(`intent_processor/mod.rs` 1968)內聚不該硬拆(borrow-checker 耦合)。兩個 225K LOC 對半=合理切分非膨脹。
- 真值得做(投報×風險排序)：①`governance_routes.py`(1978，**第一個 route 在 960 行**)抽 autonomy service=低風險同修檔案大小+route 紀律 ②`strategy_ai_routes.py` 抽 closed-PnL 分頁+demo-snapshot ③**16 個統計函數在 w_audit_8b/8c 複製貼上**(formula drift 風險)收斂 ④ PG-connect helper(≥8份)+`_safe_float`(13份)收斂 ⑤`replay_full_chain_routes.py`(1931行/2 route) 下推 `replay/`。根因：`helper_scripts/lib/` 無 Python 共用庫。
- 純清理：README+program_code/README 仍列已刪的 `program_code/{governance,risk_control,trade_executor}/`(文檔漂移)；`backups/trading_ai_pre_phase0a_20260404_180411.dump` 未 gitignore 應 `git rm`+gitignore；~1400 行 Python 可回收(h0_gate gating + reconciliation_engine/hub.reconcile() 僅測試調)**但刪前需 ssh trade-core 確認 0-caller**(Mac 靜態查不到 cron/動態 import)。

agent workspace memory 已各自更新(PA/FA/E5)。全部不擋 live gate=純維護投資,適合 design-freeze 窗口。
