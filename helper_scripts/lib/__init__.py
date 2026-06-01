"""helper_scripts 共享 Python library（offline research / report scripts 專用）。

MODULE_NOTE:
  模塊用途：為 ``helper_scripts/**`` 下的離線研究 / 報告腳本提供共享 helper，
    消除跨腳本 copy-paste（E5 findings #3 stats 整併 + #4 shared-lib infra）。
    在此 package 出現前 ``helper_scripts/lib/`` 只放 shell script，沒有 Python
    shared lib，導致報告腳本各自複製 PG 連線 + 統計公式。
  主要子模塊：
    - ``pg_connect``：整併報告腳本族的 PG 連線 helper（DSN 解析差異經參數保留）。
    - ``stats_common``：整併 W-AUDIT-8b / 8c / alpha_candidate 共用的統計公式
      （PSR / DSR / block-bootstrap CI / PBO / Wilson CI / skew / kurtosis）。
  依賴：純 stdlib（math/random/statistics）+ 延遲匯入 psycopg2（僅 pg_connect）。
  硬邊界：
    - 只服務 offline scripts；不得被 ``control_api_v1/app/`` runtime 模塊匯入。
    - 不引入新可變 singleton；不碰交易 / 風控 / live state。
    - 統計整併以「保留正確行為」為準；若 source 副本已 diverge，採數學正確的
      canonical 版並標註（見 ``stats_common`` 模塊註解）。
"""
