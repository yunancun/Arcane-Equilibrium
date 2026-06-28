from pathlib import Path


STATIC_DIR = Path(__file__).resolve().parents[2] / "app" / "static"


def _read(name: str) -> str:
    return (STATIC_DIR / name).read_text(encoding="utf-8")


def test_demo_fill_history_loads_when_collapsible_opens() -> None:
    demo = _read("tab-demo.html")

    assert 'id="demo-fills-collapse"' in demo
    assert 'ontoggle="onDemoFillsToggle(this)"' in demo
    assert "function onDemoFillsToggle(el)" in demo
    assert "loadDemoFills();" in demo
    assert "const qs = '?limit=' + _demoFillState.limit" in demo
    assert "const fastPrefix =" not in demo


def test_closed_pnl_time_uses_date_time_formatter_in_demo_and_live() -> None:
    common_formatters = _read("common-formatters.js")
    demo = _read("tab-demo.html")
    live = _read("tab-live.js")
    formatter_body = common_formatters.split("function ocFillDateTime(ts)", 1)[1].split(
        "\n}\n\nfunction ocPnlClass",
        1,
    )[0]

    assert "function ocFillDateTime(ts)" in common_formatters
    assert "const utcDay = p(d.getUTCMonth() + 1) + '-' + p(d.getUTCDate());" in formatter_body
    assert "getUTCFullYear" not in formatter_body
    assert "localDate" not in formatter_body
    assert "' UTC (local: ' + p(d.getHours())" in formatter_body
    assert "平倉日期時間" in demo
    assert "ocFillDateTime(updated)" in demo
    assert "平倉日期時間" in live
    assert "ocFillDateTime(updated)" in live


def test_demo_and_live_fill_tables_use_wide_history_layout() -> None:
    common = _read("common.js")
    demo = _read("tab-demo.html")
    live = _read("tab-live.html")

    assert ".oc-fill-table { min-width: 1080px; }" in common
    assert 'class="oc-table oc-fill-table"' in demo
    assert 'class="live-table oc-fill-table"' in live
