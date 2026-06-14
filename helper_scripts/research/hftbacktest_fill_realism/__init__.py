"""hftbacktest fill-realism harness（artifact-only 離線回測，D2 re-validation）。

MODULE_NOTE:
  模塊用途：用 hftbacktest 在 Tardis 免費 first-day-of-month L2/trade tape 上
    反事實模擬「反 cascade 的 passive maker 限價單」之 fill 率、queue position、
    成交後逆選擇，扣 maker fee（**rebate 鐵則 = 0**）後算 net，把 D2
    （liquidation-cascade delta-中性 LP 收斂候選）的「離線 alpha 存在但疑非可
    捕捉」之猜測變數據裁決：HARVESTABLE / NON-HARVESTABLE / INSUFFICIENT_SAMPLE。
  主要模塊：
    - data_fetch：Tardis 免費 CSV.gz 下載（無 key，host allowlist + 禁 redirect）
      → PIT append-only run dir/raw/（重名 raise，禁回填）。
    - converter：Tardis CSV → hftbacktest 8-field event npz（首選官方
      `hftbacktest.data.utils.tardis.convert`，trades 在 depth 前 = queue 雙扣防護）。
    - harness：建 BacktestAsset（log_prob queue model + flat per-trade fee）跑
      離線 maker fill 模擬。
    - bridge_d2：read-only 我們 market.liquidations 構造 cascade 事件
      ∩ Tardis 同窗 → 每事件掛反 cascade passive maker 單 → fill/queue/逆選擇
      → net（禁 rebate）→ d2_revalidation.json 裁決。
    - artifact：append-only run dir + manifest + sha256 index（mirror
      deribit_vol_axis / aeg_execution_realism）。
    - cli：fetch / convert / simulate / revalidate-d2 入口，dry-run 默認。
  依賴：Python 標準庫 + numpy + hftbacktest（2.x，PyPI；同引擎 Rust 核心，
    PA design §2.2 授權的務實降級——離線研究膠水非生產路徑）；market.liquidations
    讀取用 psycopg（僅 bridge_d2 read-only，且強制 set_session(readonly=True)）。

  定位鐵則（CLAUDE 一/四 + ADR market-data 例外，mirror deribit_vol_axis）：
    - Bybit 是唯一 EXECUTION 交易所；Tardis 僅作 ADR 允許的 read-only 市場數據
      來源（與 Deribit 同性質）。本 harness 不碰 live、不碰執行路徑、不碰 5-gate、
      不碰 order_manager.rs、不碰 IPC、不需 restart_all。
    - artifact-only：不建 PG 表（避 V### migration），唯一輸出 = filesystem
      run dir。market.liquidations 僅 read-only 讀（bridge_d2 構造事件源）。
    - PIT append-only：每次採集/模擬 = 新 run dir，禁回填、禁覆寫（snapshot 是
      當時 L2 tape 的唯一 point-in-time 來源，覆寫 = 不可逆毀證）。
    - host allowlist 只含 datasets.tardis.dev：結構性排除任何 private/下單 endpoint。
    - artifact root 禁硬編碼：${OPENCLAW_DATA_DIR:-/tmp/openclaw}/ 推導。

  net 計算 DECISIVE BLOCKER（approved-MM 資格鐵則，全評不可逾越）：
    OpenClaw **物理上收不到 maker rebate**——任何路徑滲入正 rebate = 把
    fake-positive edge 推下游 = 用錢自動化負期望。故 ``MAKER_REBATE_BPS`` 寫死
    0.0，CLI 不可覆寫為負，且 ``assert_no_rebate`` 在任何 rebate>0 配置即 raise。

  誠實鐵則（Tardis 免費 = 每月 1 號單日）：
    免費樣本只能可靠裁 NON-HARVESTABLE（fill_rate 致命低是小樣本即穩健的結論）；
    HARVESTABLE 是會驅動 fork-A 建執行架構的高後果結論，**需大樣本**——free-sample
    成交事件數 < ``MIN_HARVESTABLE_FILLED_EVENTS`` 時 verdict 強制
    INSUFFICIENT_SAMPLE 或 NON-HARVESTABLE，禁吐 HARVESTABLE。
    **未成交的 maker 單必計入 fill_rate 分母**（D2 non-harvestable 假說核心 =
    掛單接不到 cascade 對手盤）。
"""

from __future__ import annotations

RUNNER_VERSION = "hftbacktest_fill_realism.v0.1"

# artifact schema 版本（mirror deribit_vol_axis 版本常數慣例）。
FILL_REALISM_SCHEMA_VERSION = "hftbacktest.fill_realism.v0.1"
D2_REVALIDATION_SCHEMA_VERSION = "hftbacktest.d2_revalidation.v0.1"
MANIFEST_SCHEMA_VERSION = "hftbacktest.fill_realism_manifest.v0.1"
ARTIFACT_INDEX_SCHEMA_VERSION = "hftbacktest.fill_realism_artifact_index.v0.1"

# Tardis 免費 first-day-of-month CSV 的數據通道（Bybit linear USDT perp）。
TARDIS_EXCHANGE = "bybit"
# converter 需 trades 在 depth 之前（官方契約：避免 queue position 雙扣——
# depth message 已扣掉成交量，後到的 trade message 又扣一次）。
TARDIS_CHANNELS = ("incremental_book_L2", "trades", "liquidations")

# ---------------------------------------------------------------------------
# fee 模型（DECISIVE BLOCKER 執行點）
# ---------------------------------------------------------------------------
# Standard tier maker fee = 2 bps/leg（與 account_manager.rs DEFAULT_MAKER_FEE
# = 0.0002 一致）。taker 對照腳 = 5.5 bps round-trip（D2 已知 taker net −21.66bps
# 的成本腳，與 four-lens 成本修正對照）。
MAKER_FEE_BPS_PER_LEG = 2.0
TAKER_FEE_BPS_PER_LEG = 2.75
# rebate 鐵則：寫死 0.0，禁覆寫為正/負。OpenClaw 非 approved-MM，收不到 rebate。
MAKER_REBATE_BPS = 0.0

# ---------------------------------------------------------------------------
# D2 cascade 事件偵測 + 裁決門檻
# ---------------------------------------------------------------------------
# cascade = 同方向強平在時間窗內聚類 + 累積 qty 過閾值（時間聚類 + qty 閾值 + 方向）。
CASCADE_CLUSTER_WINDOW_S_DEFAULT = 30.0
CASCADE_MIN_EVENTS_DEFAULT = 3
# D2 半衰期窗：離線分析 H3→H20→0，time-based exit 取保守 5 分鐘收斂窗。
D2_EXIT_HORIZON_S_DEFAULT = 300.0

# 裁決門檻（誠實鐵則）：
# - HARVESTABLE 需「成交事件數 >= MIN_HARVESTABLE_FILLED_EVENTS」（大樣本）。
#   Tardis 免費單日通常達不到 → 結構性導向 INSUFFICIENT_SAMPLE / NON-HARVESTABLE。
# - fill_rate < FILL_RATE_FATAL_FLOOR = 致命低 = 掛單接不到 → NON-HARVESTABLE
#   （小樣本即穩健，承 PA design §3.3）。
MIN_HARVESTABLE_FILLED_EVENTS = 30
FILL_RATE_FATAL_FLOOR = 0.30

VERDICT_HARVESTABLE = "HARVESTABLE"
VERDICT_NON_HARVESTABLE = "NON-HARVESTABLE"
VERDICT_INSUFFICIENT_SAMPLE = "INSUFFICIENT-SAMPLE"
VERDICT_BLOCKED = "BLOCKED"

# Tardis datasets host allowlist（唯讀公開數據集；結構性排除任何 auth/下單 host）。
TARDIS_DATASETS_HOST = "datasets.tardis.dev"


class RebateForbiddenError(ValueError):
    """maker rebate 配置 > 0 / < 0 = 違 approved-MM DECISIVE BLOCKER 鐵則。"""


def assert_no_rebate(rebate_bps: float) -> None:
    """net 計算前的鐵則守衛：rebate 必須恰為 0.0，否則 raise。

    為什麼 fail-closed：OpenClaw 物理上收不到 maker rebate；任何正 rebate 會把
    fake-positive edge 推下游，用錢自動化負期望（全評 DECISIVE BLOCKER）。允許
    rebate>0 的配置滲入是本 harness 最致命的失效模式，故在 net 計算入口硬擋。
    """
    if rebate_bps != 0.0:
        raise RebateForbiddenError(
            f"maker rebate 必須為 0.0（approved-MM DECISIVE BLOCKER），收到 {rebate_bps!r}"
        )


__all__ = [
    "ARTIFACT_INDEX_SCHEMA_VERSION",
    "CASCADE_CLUSTER_WINDOW_S_DEFAULT",
    "CASCADE_MIN_EVENTS_DEFAULT",
    "D2_EXIT_HORIZON_S_DEFAULT",
    "D2_REVALIDATION_SCHEMA_VERSION",
    "FILL_RATE_FATAL_FLOOR",
    "FILL_REALISM_SCHEMA_VERSION",
    "MAKER_FEE_BPS_PER_LEG",
    "MAKER_REBATE_BPS",
    "MANIFEST_SCHEMA_VERSION",
    "MIN_HARVESTABLE_FILLED_EVENTS",
    "RUNNER_VERSION",
    "RebateForbiddenError",
    "TAKER_FEE_BPS_PER_LEG",
    "TARDIS_CHANNELS",
    "TARDIS_DATASETS_HOST",
    "TARDIS_EXCHANGE",
    "VERDICT_BLOCKED",
    "VERDICT_HARVESTABLE",
    "VERDICT_INSUFFICIENT_SAMPLE",
    "VERDICT_NON_HARVESTABLE",
    "assert_no_rebate",
]
