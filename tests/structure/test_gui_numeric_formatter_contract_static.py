"""P0.3 batch B0 formatter 契約守衛(鎖精度 dp + 第二通道結構,防未來悄改)。

為什麼用 node 執行:common-formatters.js 是 browser vanilla JS(全域函式,無 export),
契約由渲染輸出定義。用 pytest 殼出 node,注入 ocFxConvert/ocCurrSymbol stub(真值在
common.js),載入整檔後對 06_numerics.md §5.2 的斷言逐條檢核。任一 dp/符號漂移即紅。

斷言對照 06_numerics.md §5.2:
- ocPct(0.1234) === '12.34%'(fraction,2dp)
- ocPctVal(18.4) === '18.40%'(already-percent,2dp)
- ocBps(11.4) === '11.40 bps';ocBps(0) === '0.00 bps'
- ocQty(0.001234) === '0.001234'(6dp,無千分位)
- ocMoney(-3.5) 含 U+2212 且不含 ASCII '-'
- ocMoney(null)/ocBalance(NaN)/ocQty(undefined) === OC_EMPTY(U+2014)
- ocSignParts(-2).sign === U+2212 且 .cls === 'val-neg'
- ocSide('Buy') 含 'LONG' 與 'side-long'
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FORMATTERS = (
    REPO_ROOT
    / "program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/common-formatters.js"
)

# common.js 提供的依賴 stub:ocFxConvert 恆等(不換匯)、ocCurrSymbol 空字串
# (使金額斷言只驗數字/符號,不受幣別前綴干擾)。
_STUBS = """
function ocFxConvert(v){ return Number(v); }
function ocCurrSymbol(){ return ''; }
const assert = require('assert');
"""

# 斷言以 \\uXXXX 明碼寫 U+2212(−)與 U+2014(—),避免測試檔編碼歧義;
# 被測檔本身用真 glyph,由 node 執行時比對。
_ASSERTS = r"""
assert.strictEqual(ocPct(0.1234), '12.34%', 'ocPct fraction 2dp');
assert.strictEqual(ocPctVal(18.4), '18.40%', 'ocPctVal already-% 2dp');
assert.strictEqual(ocBps(11.4), '11.40 bps', 'ocBps 2dp');
assert.strictEqual(ocBps(0), '0.00 bps', 'ocBps zero');
assert.strictEqual(ocQty(0.001234), '0.001234', 'ocQty 6dp no thousands');

const money = ocMoney(-3.5);
assert.ok(money.indexOf('−') >= 0, 'ocMoney(-3.5) 含 U+2212 minus');
assert.ok(money.indexOf('-') < 0, 'ocMoney(-3.5) 不含 ASCII hyphen');

assert.strictEqual(OC_EMPTY, '—', 'OC_EMPTY 為 U+2014 em-dash');
assert.strictEqual(ocMoney(null), OC_EMPTY, 'ocMoney(null) → OC_EMPTY');
assert.strictEqual(ocBalance(NaN), OC_EMPTY, 'ocBalance(NaN) → OC_EMPTY');
assert.strictEqual(ocQty(undefined), OC_EMPTY, 'ocQty(undefined) → OC_EMPTY');

const sp = ocSignParts(-2);
assert.strictEqual(sp.sign, '−', 'ocSignParts(-2).sign U+2212');
assert.strictEqual(sp.cls, 'val-neg', 'ocSignParts(-2).cls val-neg');
assert.strictEqual(ocSignParts(2).cls, 'val-pos', 'ocSignParts(2).cls val-pos');
assert.strictEqual(ocSignParts(0).cls, 'val-flat', 'ocSignParts(0).cls val-flat');
assert.strictEqual(ocSignParts(0).sign, '·', 'ocSignParts(0).sign middot');

const buy = ocSide('Buy');
assert.ok(buy.indexOf('LONG') >= 0, "ocSide('Buy') 含 LONG");
assert.ok(buy.indexOf('side-long') >= 0, "ocSide('Buy') 含 side-long");
const sell = ocSide('Sell');
assert.ok(sell.indexOf('SHORT') >= 0, "ocSide('Sell') 含 SHORT");
assert.ok(sell.indexOf('side-short') >= 0, "ocSide('Sell') 含 side-short");
assert.strictEqual(ocSide('weird'), OC_EMPTY, 'ocSide 未知 → OC_EMPTY');

// signed ocBps 負號用 U+2212(canon 3)
assert.strictEqual(ocBps(-11.4, true), '−11.40 bps', 'ocBps signed neg U+2212');
assert.strictEqual(ocBps(11.4, true), '+11.40 bps', 'ocBps signed pos +');

// ocIsBlank sentinel-agnostic(null/''/'--'/'—' 皆 true,實值 false)
assert.strictEqual(ocIsBlank('--'), true, "ocIsBlank('--')");
assert.strictEqual(ocIsBlank(''), true, "ocIsBlank('')");
assert.strictEqual(ocIsBlank('—'), true, 'ocIsBlank(em-dash)');
assert.strictEqual(ocIsBlank(null), true, 'ocIsBlank(null)');
assert.strictEqual(ocIsBlank('grid_trading'), false, 'ocIsBlank(real value)');

console.log('OC_FORMATTER_CONTRACT_OK');
"""


def _run_node(harness: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["node", "-"],
        input=harness,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_numeric_formatter_contract_assertions_pass() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node 不可用;GUI JS 契約守衛需 node 執行(與 node --check 同前提)")
    assert FORMATTERS.exists(), f"找不到 common-formatters.js: {FORMATTERS}"
    src = FORMATTERS.read_text(encoding="utf-8")
    harness = _STUBS + "\n" + src + "\n" + _ASSERTS
    result = _run_node(harness)
    assert result.returncode == 0, (
        "formatter 契約斷言失敗(dp/符號漂移?):\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    assert "OC_FORMATTER_CONTRACT_OK" in result.stdout, (
        f"守衛未跑到結尾(斷言中途中斷?):stdout={result.stdout!r}"
    )
