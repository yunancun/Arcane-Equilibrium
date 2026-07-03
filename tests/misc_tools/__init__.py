# 為什麼需要本檔: tests/local_model_tools/test_pure_utils.py 與本目錄
# test_pure_utils.py 同 basename,pytest 預設 prepend import mode 下兩者都想
# 以頂層模組名 `test_pure_utils` import → collection「import file mismatch」
# 互斥中斷。加 __init__.py 後本檔以 `misc_tools.test_pure_utils` 收集,重名
# 消解(鏡像 tests/ml_training/__init__.py 既有解法)。
# 注意: 不可反向加在 tests/local_model_tools/——那會令頂層 package 名
# `local_model_tools` 遮蔽真正的 program_code/local_model_tools,使其
# `from local_model_tools.hurst_exponent import ...` 假紅。
