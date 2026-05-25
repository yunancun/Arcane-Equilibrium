"""
MODULE_NOTE
模塊用途：M4 Stage 1 Source-5 (Token Unlocks) STUB — Sprint 3+ 才實裝。

per W1-B spec §1.5：
   - Stage 1 Sprint 2 = NOT IMPL（per Sprint 2 dispatch packet §3.2 AC-S2-B-1
     "4 input source...token unlock 留 Sprint 3+"）
   - 本 stub raise NotImplementedError 不靜默返回 empty df
   - Sprint 3+: 接 Tokenomist API / DropsTab / CoinMarketCap unlock calendar
     + landed cache table (V### Sprint 3)

為什麼 fail-loud raise：靜默 return empty df 會讓 Sprint 2 IMPL 假裝接通了
Source-5（per AC-S2-B-1 misleading 'pass'）。fail-loud 強制 caller 知道
此 source 仍 stub，5 source 在 Sprint 2 內只接通 4。
"""
from __future__ import annotations


class TokenUnlocksNotImplementedError(NotImplementedError):
    """Source-5 Token Unlocks 在 Sprint 2 未實裝。

    Sprint 3+ 需要接：
       - Tokenomist API（https://tokenomist.io/api/）
       - DropsTab API（https://dropstab.com/api/）
       - CoinMarketCap unlock calendar
    + landed cache table（V### Sprint 3）。
    """


def load_token_unlocks(*args, **kwargs):
    """Stub — raise NotImplementedError。

    Sprint 3+ IMPL 接此 entry point 即可（不變 signature）。
    """
    raise TokenUnlocksNotImplementedError(
        "Source-5 Token Unlocks 是 Sprint 3+ scope；Sprint 2 dispatch packet "
        "§3.2 AC-S2-B-1 明示 token unlock 留 Sprint 3+。"
        "如需 Sprint 2 提早接通，請走 PA dispatch RFC 路徑改 W1-B spec §1.5。"
    )
