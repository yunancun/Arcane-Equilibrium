"""program_code.research — 研究產出器（read-only、純函數核心）。

MODULE_NOTE
模塊用途：研究層 producer 套件（非交易真相層）。目前含 altcap_basket（L2 P3b B1 的第二
  因子：equal-weight ex-BTC CORE25 籃子報酬）。所有 producer read-only、leak-free-by-
  construction，0 order path。
硬邊界：本套件不寫交易/風控狀態；只 SELECT market data + FND-2 membership 算研究序列。
"""
