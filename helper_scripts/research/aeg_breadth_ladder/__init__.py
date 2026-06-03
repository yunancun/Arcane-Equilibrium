"""AEG-S2 component (b) breadth ladder runner — package marker + 版本常數。

MODULE_NOTE:
  模塊用途：AEG-S2 breadth ladder runner。把**任一候選的 per-symbol PnL 生成**在
    FND-2 PIT universe 的 4 個 breadth tier（core25_pinned ⊂ top_liquidity_40_50 ⊂
    full_survivorship，外加 scanner_active_asof overlap）上各跑一次，產 deterministic
    ``breadth_ladder.parquet``（S0 §1.3），報 per-tier net edge + significance +
    **monotonicity**（edge 隨 breadth 加寬存活，還是塌成 1-2 symbol fluke）。是 (c)
    robustness matrix ``breadth_cohort`` 軸的證據源。
  子模塊：
    - ``tiers`` — 凍結 ``BREADTH_TIERS`` 定義 + ``assemble_tiers``（從 FND-2
      ``cohort_ids`` multi-membership 組 cumulative-nested set）+ nested 不變量斷言。
    - ``universe_artifact`` — 讀 FND-2 universe.csv/.parquet（``included`` /
      ``cohort_ids`` / ``alive_from`` / ``alive_to`` / ``seen_delisted``）+ 組
      alive_mask（survivorship 繼承，不重算）。0 DB（讀檔）。
    - ``ladder`` — 純函數核心：{tier→TierResult}→per-tier net edge + significance +
      monotonicity 判定 + **breadth≠n_independent 分離** + ladder rows/summary +
      ``ladder_id`` digest。0 DB / 0 候選耦合。
    - ``evaluator`` — ``CandidateEvaluator`` protocol + ``TierResult`` schema +
      multiday reference adapter（包既有候選 harness 為 per-tier evaluate）。
    - ``artifact`` — breadth_ladder.csv/.parquet + summary.json + manifest.json +
      artifact_index.json + sha256 + ``ladder_id`` digest（mirror FND-2 artifact）。
    - ``harness`` — CLI 編排（顯式窗無隱式 now()）。
  硬邊界（read-from-storage-only，PM 已裁 S2=read-from-storage-only）：
    - read-only：universe 來自 FND-2 artifact（讀檔）；價格/funding 由候選 harness 經
      ``set_session(readonly=True)`` 讀 S1-stored ``market.*``。0 DB write / 0 backfill
      / 0 schema / 0 migration / 0 IPC / 0 auth / 0 order。絕不重抓 Bybit。
    - **survivorship 繼承不重算**：``alive_from_utc`` / ``alive_to_utc`` 從 FND-2
      artifact 繼承（MIT b.2）；(b) 0 自寫 listed_at 查詢。禁 current-survivor 捷徑。
    - **breadth ≠ n_independent**：加寬 breadth 報 symbol-count per tier，但
      ``n_independent`` 保持 time-cluster-bound，絕不隨 symbol 數膨脹（S0 §2.9 +
      cost-wall 8-rebalance 牆）。
    - **tier 組裝用 ``cohort_ids``（multi-membership）NOT ``recommended_tier``
      （single-pick）**：breadth ladder 是嵌套累加，core25 成員須同時在更寬 tier。
    - 絕不 import ``control_api_v1/app/`` runtime 模組（artifact 紅線同 FND-2）。
  依賴：標準庫 + numpy（候選 adapter）+ psycopg2（候選 loader 延遲 import）；parquet
    經 duckdb（延遲 import，缺套件時鏡像 skip，csv 為 SoT）。
"""

from __future__ import annotations

# breadth tier 定義 + ladder 演算法版本。任一影響 ladder_id digest 的契約變更（tier
# 成員規則、monotonicity 判定、欄序）都必須升版，否則 determinism / monotonicity 對帳
# 會誤判（S0 manifest §1.4 保留 aeg_breadth_v0.1.0；MIT b.4）。
BREADTH_LADDER_VERSION = "aeg_breadth_v0.1.0"

# breadth_ladder 行 artifact schema 版本（進 artifact_index）。
LADDER_SCHEMA_VERSION = "aeg.breadth_ladder.v0.1"

# artifact manifest schema（AEG-S0 §1.4 對齊，與 FND-2 同 schema 字串）。
MANIFEST_SCHEMA_VERSION = "aeg.alpha_history_run_manifest.v0.1"

# S0 §2.9 gate 3：n_independent >= 30 才算足夠樣本（cost-wall 8-rebalance 牆的機械化）。
N_INDEPENDENT_PROMOTION_FLOOR = 30

__all__ = [
    "BREADTH_LADDER_VERSION",
    "LADDER_SCHEMA_VERSION",
    "MANIFEST_SCHEMA_VERSION",
    "N_INDEPENDENT_PROMOTION_FLOOR",
]
