---
name: project-2026-06-10-half-life-scipy-lane-fix
description: "half_life 測試 2F 根因=trade-core 系統 python 無 scipy(非日期/seed/容差);修=importorskip 守衛,landed main 5421897e;附 Linux 測試 lane 拓撲與 ledger 歸屬知識"
metadata: 
  node_type: memory
  type: project
  originSessionId: 6fdb93b1-b990-42fd-ba9c-41be85afdc78
---

# half_life 測試腐化修復 + Linux 測試 lane 拓撲 (2026-06-10)

**結案**:`test_pnl_decay_pass`/`test_sharpe_decay_pass` 2F 根因=trade-core `/usr/bin/python3` 無 scipy → estimator `_SCIPY_AVAILABLE=False` 設計性降級 `default_14d` → `method_used` 斷言 FAIL。operator 三個初始假說(日期敏感/隨機種子/數值容差)**全偽**——fixture 固定 seed+固定 base_ts,estimator 無 wall-clock。

**修**(E1→E2 APPROVE→E4 PASS,main `dc5c60d7`+`6c8c40b4`+報告 `5421897e`):兩 fit-path 測試加 `pytest.importorskip("scipy")`(比照 test_onnx_exporter_quantile 慣例)+ requirements-ml.txt 顯式宣告 `scipy>=1.10.0`。斷言語意零改動。estimator 不動(降級 by-design,`_regime_math.py` 同款守衛)。修後:scipy-less lane **5p+2s**,有-scipy lane **7p**(Linux venv scipy 1.17.1/numpy 2.4.6/pandas 3.0.3 實證,未來 un-skip 不會炸)。

**Linux 測試 lane 拓撲**(future triage 用):
- `/usr/bin/python3`(系統,py3.12.3):numpy 2.4.4+pandas via pip --user `~/.local`,**無 scipy**;是 operator 跑 pytest 的 lane
- control_api `.venv`:**有 scipy 1.17.1**(sklearn 轉依賴)
- `~/.venv`(py3.12):有 scipy 無 pytest
- scipy 生產使用面僅 2 檔:`half_life_estimator.py`/`_regime_math.py`,皆有 try/except 降級守衛;**0 生產 caller** import half_life_estimator(fixture-driven,待 FUP-2)

**Ledger 歸屬更正**(E4):此 2F **不屬**「full 4661/8 pre-existing」(該 ledger≈`tests/` 控制面 scope;root 裸收集 7325+3err);屬 06-10 producer-gate ledger(794p/2f→修後 794p/0f+2s)。8-ledger 不變。

**教訓**:失敗模式=「恰好重依賴 fit-path 測試 FAIL、降級路徑全綠」→ 先查 optional-dep 靜默降級(env lane 差異),再考慮日期/seed/容差。RCA 雙向驗證法:同檔在無 scipy lane 重現 FAIL+有 scipy lane 7p,一次定根因。

**殘留清零(06-10 operator 拍板後)**:runtime scipy 1.17.1 已實裝(`pip install --user --break-system-packages`,PEP 668 須加 flag),`/usr/bin/python3` lane 該檔 **7 passed** un-skip 實證;remote branch `fix/half-life-test-scipy-skip` 已刪(全併 main)。Linux lane 拓撲第一行更新:系統 python **現有 scipy**。

關聯:[[project_2026_06_08_l2_d3_phase1_green]](4661/8 ledger 出處)、[[feedback_fetch_before_dispatch]](本次 main 兩次 fetch 間被推進,re-fetch 救了 ff push)
