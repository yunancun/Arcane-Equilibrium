"""alpha_wealth_controller — L2 P4 online-FDR α-wealth 純數學核心（M1）。

MODULE_NOTE
模塊用途：α-investing（Foster & Stine 2008 GAI 變體）的 wealth 帳務純函數核心。
  family 初始 wealth 鑄造、per-test α_i 指派（含 cap 與數值 floor）、可測性判定、
  φ-proportional refund 金額、α_i→DSR threshold 映射（Option B）、demo-confirm
  三值裁決。供 PG 帳本層（control_api `l2_alpha_wealth_store`）與 refund
  reconciler（ml_training）消費；wealth 真值在 PG，本模組零狀態。
主要函數：init_family_wealth / assign_alpha_i / can_test / refund_amount /
  dsr_threshold_for / demo_confirm_verdict。
依賴：標準庫 math 而已（0 numpy / 0 DB / 0 I/O / 0 async / 0 psycopg2）。
硬邊界：純函數、無副作用、不觸碰任何 live/tier/lease 面；所有失敗方向收縮
  （None / "pending" / ValueError fail-loud），永不放寬既有 gate。

設計契約：PA P4 設計 §2.2（六簽名為契約）+ MIT M1+M2 final ratification 折入
  （#1 NOTE 1b 數值 floor、#2 Option B 拍板、#7 NOTE 7a/7b/7c docstring 義務）。

數學骨架（MIT §1 自含推導的三前提，本模組負責前兩個的機械面）：
  (a) α_i 在 test 前由 PG balance 決定（predictable）——assign_alpha_i 是 balance
      的確定函數；
  (b) per-test type-I level ≤ α_i——dsr_threshold_for 以 max(floor, 1−α_i) 接通
      DSR threshold（Option B），單調只嚴不鬆；
  (c) conducted-test-pays 由 E1-B debit 條件落實（非本模組範圍）。
  淨支出恆等式：φ=1.0 refund 只在 demo-confirmed（confirmed ⊂ discoveries）
  ⇒ W_t ≤ W_0 恆成立、per-family mFDR ≤ max(W_0, cap) = 0.1·α_target。
"""

from __future__ import annotations

import math
from typing import Literal

# ─────────────────────────────────────────────────────────────────────────────
# M1 ENDORSED 常數（PA §2.2；MIT ratify #1/#7）
# ─────────────────────────────────────────────────────────────────────────────

# 名目 FDR target（family_init 事件 evidence 持久化當時值）。
ALPHA_TARGET_DEFAULT: float = 0.05

# M1：W_0 = 0.10 · α_target（比 LORD 慣例 W_0 ≤ α 更緊）。
W0_GAMMA: float = 0.10

# M1：proportional refund 比例（φ=1.0 = exactly self-funding：refund 恰補回
# 已扣額，wealth 永不超過 W_0——MIT §1 淨支出恆等式前提）。
PHI_REFUND: float = 1.0

# M1 NOTE（MIT ratify #7）：α_i ≤ α_target / min_batch_size 的 cap 除數。
#
# 命名消歧（MIT 7b）：`min_batch_size` 不是 batch-BH（批次晉升）語義——它是
# per-test cap 的除數：「任何單一 test 不得消耗超過總 FDR target 的
# 1/min_batch_size」。M1 ENDORSED 用此名故不改名，僅在此消歧。
#
# defense-in-depth, not operative（MIT 7a）：默認動態下 α_i = 0.10·W_t 且
# W_t ≤ W_0 = 0.005 ⇒ α_i ≤ 5e-4 恆小於 cap = α_target/10 = 0.005，cap 永不
# binding；唯 operator_adjustment 把 wealth 抬過 0.05 後 cap 才 binding——
# 這正是它存在的理由（防 operator 手滑灌 wealth 後單 test 吃掉半個 target）。
MIN_BATCH_SIZE_DEFAULT: int = 10

# PA default α_i 序列：α_i = min(0.10·W_t, cap)（MIT ratify #1：合法 GAI
# proportional spending rule；幾何衰減軌跡使 Σα_i ≤ W_0 自動成立）。
SPEND_FRACTION_DEFAULT: float = 0.10

# M1 demo-confirm 帳務 bar（refund 觸發所需最小 demo round-trip 數）。
#
# 30 vs 50 並排講清（MIT 點名的 M1 NOTE 文檔義務）：
#   - REFUND_MIN_TRADES = 30：refund「帳務」bar——demo 部署後累積 ≥30 筆
#     round-trip 才允許 reconciler 渲染 confirmed/failed 結論性裁決；管的是
#     「一筆已扣 α 債何時可以退款/銷帳」，是 wealth 帳本事件的觸發條件。
#   - `_Q1_MIN_TRADES_OOS = 50`（l2_ml_advisory_executor 既有常數）：math gate
#     Q1 stage 的「樣本前置」——OOS 樣本 < 50 → 整個 math gate DEFER、test 不
#     conducted、不扣帳；管的是「假說檢定本身有沒有資格被執行」。
#   兩者作用在不同階段（refund 帳務 vs 假說檢定前置）、不同資料（demo 部署後
#   forward fills vs 候選 evidence OOS 樣本），數值獨立、不可互相替代。
REFUND_MIN_TRADES: int = 30

# B2：demo-confirm 所需最小 forward-OOS 日曆天數（posture-independent）。
# 唯一定義點——E1-C refund reconciler 與未來任何 auto-promote applier 必須
# import 本常數，禁止各處複製字面 21（PA §7 B2 enforcement 契約條款）。
MIN_FORWARD_OOS_DAYS: int = 21

# MIT 1b + 7c：α_i 數值 floor。算出的 α_i 低於此值 ⇒ assign_alpha_i 回 None
# （slot 不可測）。一石二鳥：
#   (1b) 解殭屍 family——純比例 spend 下 W−α_i = 0.9·W > 0 恆真、can_test 永真，
#        family 連跌後 α_i→0、threshold→1，淪為「永遠可測但永遠不可能 pass」
#        的殭屍態；floor 給出有限 α-death（None ⇒ DEFER，誠實熄燈）。
#   (7c) 防 NUMERIC(14,10) underflow fail-loud——α_i = 5e-4·0.9^t 在 t≈150 跌破
#        1e-10 存儲精度 → 取整為 0 → V138 `awl_amount_sign_chk`（debit 必 <0）
#        被違反 → INSERT 炸。floor 在源頭擋住，債永不縮到精度之下。
ALPHA_I_MIN_FLOOR: float = 1e-6

# DSR threshold floor（= dsr_gate.DEFAULT_DSR_THRESHOLD 的字面對齊；不 import
# control 流以保 0 依賴）。MIT #2：max(0.95,·) ≥ 0.95 = 今日 gate ⇒ 映射永不
# 比現狀寬（root principle 5/6 單調只嚴不鬆）。
DSR_THRESHOLD_FLOOR: float = 0.95


# ─────────────────────────────────────────────────────────────────────────────
# 純函數核心（PA §2.2 六簽名）
# ─────────────────────────────────────────────────────────────────────────────


def init_family_wealth(
    alpha_target: float = ALPHA_TARGET_DEFAULT, gamma: float = W0_GAMMA
) -> float:
    """鑄造 family 初始 wealth：W_0 = gamma · alpha_target。

    為什麼限 gamma ∈ (0, 1]：W_0 ≤ α_target 是 mFDR bound 的前提之一
    （文獻慣例 W_0 ≤ α；本設計 W_0 = 0.1·α_target 更緊）。gamma > 1 等於
    開局鑄超額 wealth，破壞 MIT §1「W_t ≤ W_0 ≤ α_target 量級」的保守結構。

    參數非法（非有限 / alpha_target ∉ (0,1) / gamma ∉ (0,1]）→ ValueError
    fail-loud：W_0 鑄造是 family_init 帳本事件的金額來源，靜默修正會污染
    append-only 帳本，必須在源頭炸。
    """
    if not (math.isfinite(alpha_target) and 0.0 < alpha_target < 1.0):
        raise ValueError(f"alpha_target={alpha_target} 必須在 (0, 1) 內")
    if not (math.isfinite(gamma) and 0.0 < gamma <= 1.0):
        raise ValueError(f"gamma={gamma} 必須在 (0, 1] 內")
    return gamma * alpha_target


def assign_alpha_i(
    balance: float,
    *,
    alpha_target: float,
    min_batch_size: int,
    spend_fraction: float,
) -> float | None:
    """由當前 PG balance 指派本次 test 的 α_i；None ⇒ 本 slot 不可測。

    規則（MIT ratify #1 + #7 + 1b 折入）：
      α_i = min(spend_fraction · balance, alpha_target / min_batch_size)
      若 α_i < ALPHA_I_MIN_FLOOR（1e-6）→ None（slot 不可測；含 balance ≤ 0
      與 balance 非有限的一切退化情形——fail-closed 收縮向）。

    predictability 前提（MIT §1 (a)）：α_i 必須在 test 前由 balance 決定。
    本函數是 balance 的確定函數、無任何隨機/時變成分，前提機械成立。

    cap 語義（MIT 7a）：默認動態下 cap 永不 binding（α_i ≤ 5e-4 < 0.005），
    它是 operator_adjustment 抬高 wealth 後的 defense-in-depth——詳
    MIN_BATCH_SIZE_DEFAULT 注釋。

    參數非法（非有限 / alpha_target ∉ (0,1) / min_batch_size < 1 /
    spend_fraction ∉ (0,1]）→ ValueError fail-loud：這些是 M1 ENDORSED 常數的
    載體，錯值=配置損壞，靜默回 None 會把配置 bug 偽裝成 wealth 枯竭。
    """
    if not (math.isfinite(alpha_target) and 0.0 < alpha_target < 1.0):
        raise ValueError(f"alpha_target={alpha_target} 必須在 (0, 1) 內")
    if min_batch_size < 1:
        raise ValueError(f"min_batch_size={min_batch_size} 必須 >= 1")
    if not (math.isfinite(spend_fraction) and 0.0 < spend_fraction <= 1.0):
        raise ValueError(f"spend_fraction={spend_fraction} 必須在 (0, 1] 內")
    # balance 是資料（PG SUM 讀回）非配置：非有限 → None（不可測），不 raise。
    if not math.isfinite(balance):
        return None
    cap = alpha_target / float(min_batch_size)
    alpha_i = min(spend_fraction * balance, cap)
    # MIT 1b/7c 數值 floor：低於 1e-6 即不可測（殭屍 family 熄燈 + NUMERIC
    # underflow 源頭防護）。balance ≤ 0 時 alpha_i ≤ 0 < floor，同路徑收掉。
    if alpha_i < ALPHA_I_MIN_FLOOR:
        return None
    return alpha_i


def can_test(balance: float, alpha_i: float) -> bool:
    """G.1.1 可測性判定：扣掉 α_i 後 wealth 會 ≤ 0 ⇒ False。

    不變量：wealth 不可負（MIT §1 淨支出恆等式的機械前提）。本判定與
    assign_alpha_i 的 floor 互補——純比例 spend 下本判定恆 True（0.9·W > 0），
    真正的有限熄燈由 floor 提供；本判定防的是「α_i 來源非 assign_alpha_i」
    的路徑（如 operator 手動注入）把帳扣穿。

    fail-closed：balance / alpha_i 非有限、或 alpha_i ≤ 0（上游契約破壞——
    assign_alpha_i 只會給 ≥ 1e-6 或 None）→ False，不渲染可測。
    """
    if not (math.isfinite(balance) and math.isfinite(alpha_i)):
        return False
    if alpha_i <= 0.0:
        return False
    return (balance - alpha_i) > 0.0


def refund_amount(alpha_debited: float, phi: float = PHI_REFUND) -> float:
    """φ-proportional refund 金額：refund = phi · alpha_debited。

    參數 alpha_debited 取「已扣 α 的正數量值」（ledger debit row 存負額，
    caller 取絕對值傳入）。

    為什麼限 phi ∈ [0, 1]：φ > 1 會使 refund 超過原扣額 ⇒ W_t 可超過 W_0，
    破壞 MIT §1「wealth 永不超過初始值」的 supermartingale 前提（refund-on-
    confirm 比文獻 reward-on-rejection 嚴格更保守的論證依賴 ψ=φ ≤ payout cap
    逐路徑成立）。M1 拍板 φ=1.0 = exactly self-funding。

    非法輸入（非有限 / alpha_debited < 0 / phi ∉ [0,1]）→ ValueError
    fail-loud：refund 金額直接進 append-only 帳本，錯值即永久壞帳。
    """
    if not (math.isfinite(alpha_debited) and alpha_debited >= 0.0):
        raise ValueError(f"alpha_debited={alpha_debited} 必須為非負有限值")
    if not (math.isfinite(phi) and 0.0 <= phi <= 1.0):
        raise ValueError(f"phi={phi} 必須在 [0, 1] 內（φ>1 破壞 W_t ≤ W_0 不變量）")
    return phi * alpha_debited


def dsr_threshold_for(alpha_i: float, *, floor: float = DSR_THRESHOLD_FLOOR) -> float:
    """α_i → DSR threshold 映射（MIT #2 拍板 Option B）：max(floor, 1−α_i)。

    語義：test 以真實 type-I level ≤ α_i 執行（DSR null 校準前提下
    P(pass | null) ≤ α_i），接通 MIT §1 前提 (b)——帳本扣的 α_i 與 test 實際
    水準恆等，FDR 語義才成立（Option A 被 MIT REJECT 正因切斷此恆等）。

    單調只嚴不鬆（root principle 5/6）：
      - floor 鎖死 ≥ 0.95 = 今日 dsr_gate 默認閾值 ⇒ 映射永不比現狀寬；
      - α_i 越小（wealth 越枯）threshold 越逼近 1 = 自然 throttle。
      reachable wealth 下 α_i ≤ 5e-4 ⇒ threshold ≥ 0.9995，初期 pass rate
      預期 ≈ 0 是設計後果非故障（MIT N-7）。

    邊界（MIT #2 親驗背書，勿「修」）：alpha_i = 0（浮點下溢）→ 回 1.0 →
    下游 DsrGate threshold 驗證 raise ValueError → math gate fail-soft DEFER
    = 收縮向不 crash。本函數不 clamp 到 <1——clamp 會把「wealth 歸零」偽裝成
    「可測但極嚴」，違背誠實熄燈語義。正常管線下 assign_alpha_i 的 floor 保證
    α_i ≥ 1e-6 ⇒ threshold ≤ 1−1e-6 < 1，不會走到此邊界。

    非法輸入 → ValueError fail-loud：alpha_i 非有限 / <0 / ≥1（α 是機率水準，
    域外即上游契約破壞）；floor 非有限 / < 0.95（floor 不可降——MIT #2）/ ≥ 1。
    floor 允許 > 0.95（更嚴合法）。
    """
    if not (math.isfinite(alpha_i) and 0.0 <= alpha_i < 1.0):
        raise ValueError(f"alpha_i={alpha_i} 必須在 [0, 1) 內")
    if not (math.isfinite(floor) and DSR_THRESHOLD_FLOOR <= floor < 1.0):
        raise ValueError(
            f"floor={floor} 必須在 [{DSR_THRESHOLD_FLOOR}, 1) 內（0.95 floor 不可降）"
        )
    return max(floor, 1.0 - alpha_i)


def demo_confirm_verdict(
    *,
    n_trades: int,
    stage0r_green: bool,
    demo_net_bps: float,
    forward_oos_days: int,
) -> Literal["confirmed", "failed", "pending"]:
    """M1 demo-confirm 三值裁決（G.1.1 直譯；reconciler 的唯一裁決函數）。

    語義（PA §2.2；有限輸入下與下列真值表恆等）：
      - confirmed ⇔ n_trades ≥ 30 AND stage0r_green AND demo_net_bps ≥ 0
                     AND forward_oos_days ≥ 21（四條全滿足）→ refund 觸發。
      - failed    ⇔ n_trades ≥ 30 AND（demo_net_bps < 0 OR NOT stage0r_green）
                     ——樣本足且結論性壞（不需等 21 天）→ debit_failed 銷帳。
      - 其餘（含 n_trades < 30）= pending：債留著，back-pressure 即設計意圖。

    confirmed = accounting-confirm（QC FIX-2.3）：這是 refund 觸發器（帳務
    事件），不是 alpha 證明——null-confirm 機率量級 15-40%，P5 晉升須另跑
    opened-OOS math gate + regime 標籤，嚴禁把 confirmed 讀成晉升證據。

    非有限 demo_net_bps（NaN/±inf = 資料損壞）：不在其上渲染結論性裁決——
      - stage0r_green=False 時仍 failed（0R 紅本身已結論性壞，與 net 值無關，
        與真值表一致）；
      - 其餘一律 pending（偏離 +inf→confirmed / −inf 與 NaN 下 `<0` 比較的
        IEEE 巧合語義；不退款=帳不膨脹、不鑄 dead-mode lesson=不污染 novelty
        失敗庫，雙向保守）。
    """
    # 樣本不足 → 一律 pending（債留著；REFUND_MIN_TRADES 是帳務 bar，
    # 與 math-gate 的 _Q1_MIN_TRADES_OOS=50 樣本前置無關——見常數注釋）。
    if n_trades < REFUND_MIN_TRADES:
        return "pending"
    # 0R 紅 = 結論性壞（與 demo_net_bps 取值無關，含非有限）。
    if not stage0r_green:
        return "failed"
    # 數值損壞 → 不下結論性裁決（保守：不退款、不銷帳、不鑄 dead-mode）。
    if not math.isfinite(demo_net_bps):
        return "pending"
    if demo_net_bps < 0.0:
        return "failed"
    if forward_oos_days >= MIN_FORWARD_OOS_DAYS:
        return "confirmed"
    return "pending"
