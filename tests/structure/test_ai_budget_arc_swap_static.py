from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TRACKER = REPO_ROOT / "rust/openclaw_engine/src/ai_budget/tracker.rs"


def test_ai_budget_config_cache_uses_arc_swap_usage_cache_uses_rwlock() -> None:
    source = TRACKER.read_text(encoding="utf-8")
    assert "use arc_swap::ArcSwap;" in source
    assert "config_cache: Arc<ArcSwap<BudgetConfig>>" in source
    assert "usage_cache: Arc<RwLock<UsageCache>>" in source
    assert "config_cache: Arc<RwLock<BudgetConfig>>" not in source
