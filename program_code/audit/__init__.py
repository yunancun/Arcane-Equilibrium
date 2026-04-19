"""Audit helpers (post-hoc, read-only).
審計輔助工具（事後歸因，僅讀取）。

MODULE_NOTE (EN): Offline audit scripts that read production DB / fills archives
  to answer "what-if" counterfactual questions. No write paths, no engine coupling.
MODULE_NOTE (中): 離線審計腳本，讀取生產 DB / fills 歸檔回答反事實「若當時如何」。
  無寫入路徑，無引擎耦合。
"""
