//! Context Distiller — Compress system state to ~520 tokens for L2 API calls
//! 上下文蒸餾器 — 壓縮系統狀態到約 520 tokens 供 L2 API 調用
//!
//! Thread-safe, pure computation, no side effects.
//! 線程安全，純計算，無副作用。

use pyo3::prelude::*;
use pyo3::types::PyDict;
use std::collections::VecDeque;
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};

/// Notable event for context distillation / 上下文蒸餾的值得注意事件
#[pyclass]
#[derive(Clone)]
pub struct NotableEvent {
    #[pyo3(get)]
    pub ts_ms: i64,
    #[pyo3(get)]
    pub event_type: String,
    #[pyo3(get)]
    pub summary: String,
    #[pyo3(get)]
    pub severity: String,
}

#[pymethods]
impl NotableEvent {
    #[new]
    #[pyo3(signature = (event_type, summary, severity=None))]
    fn new(event_type: String, summary: String, severity: Option<String>) -> Self {
        let ts_ms = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_millis() as i64;
        // UTF-8 safe truncation: use char boundary, not byte slice
        // UTF-8 安全截斷：按字符邊界截取，避免多字節字符（中文等）panic
        let summary = if summary.chars().count() > 80 {
            summary.chars().take(80).collect::<String>()
        } else {
            summary
        };
        NotableEvent {
            ts_ms,
            event_type,
            summary,
            severity: severity.unwrap_or_else(|| "info".to_string()),
        }
    }

    fn to_dict(&self) -> std::collections::HashMap<String, String> {
        let mut m = std::collections::HashMap::new();
        m.insert("ts_ms".to_string(), self.ts_ms.to_string());
        m.insert("event_type".to_string(), self.event_type.clone());
        m.insert("summary".to_string(), self.summary.clone());
        m.insert("severity".to_string(), self.severity.clone());
        m
    }
}

/// Context Distiller — compresses full cycle_data to ~520 tokens
/// 上下文蒸餾器 — 將完整 cycle_data 壓縮到約 520 tokens
#[pyclass]
pub struct ContextDistiller {
    events: Mutex<VecDeque<NotableEvent>>,
    max_events: usize,
}

#[pymethods]
impl ContextDistiller {
    #[new]
    #[pyo3(signature = (max_events=20))]
    fn new(max_events: usize) -> Self {
        ContextDistiller {
            events: Mutex::new(VecDeque::with_capacity(max_events)),
            max_events,
        }
    }

    /// Record a notable event / 記錄一個值得注意的事件
    #[pyo3(signature = (event_type, summary, severity=None))]
    fn record_event(&self, event_type: String, summary: String, severity: Option<String>) {
        let event = NotableEvent::new(event_type, summary, severity);
        let mut events = self.events.lock().unwrap();
        if events.len() >= self.max_events {
            events.pop_front();
        }
        events.push_back(event);
    }

    /// Compress full cycle_data to ~520 tokens / 壓縮完整 cycle_data 到約 520 tokens
    fn distill<'py>(&self, py: Python<'py>, cycle_data: &Bound<'py, PyDict>) -> PyResult<PyObject> {
        let result = PyDict::new(py);

        // Market section / 市場區塊
        let market = self.distill_market(py, cycle_data)?;
        result.set_item("market", market)?;

        // Portfolio section / 投資組合區塊
        let portfolio = self.distill_portfolio(py, cycle_data)?;
        result.set_item("portfolio", portfolio)?;

        // Health section / 健康區塊
        let health = self.distill_health(py, cycle_data)?;
        result.set_item("health", health)?;

        // Events section / 事件區塊
        let events = self.distill_events(py)?;
        result.set_item("events", events)?;

        // Timestamp / 時間戳
        let ts = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_millis() as i64;
        result.set_item("distilled_at_ms", ts)?;

        Ok(result.into())
    }

    /// Get recent events / 獲取最近事件
    #[pyo3(signature = (limit=5))]
    fn get_recent_events(&self, limit: usize) -> Vec<NotableEvent> {
        let events = self.events.lock().unwrap();
        events.iter().rev().take(limit).cloned().collect()
    }
}

impl ContextDistiller {
    fn distill_market<'py>(
        &self,
        py: Python<'py>,
        data: &Bound<'py, PyDict>,
    ) -> PyResult<PyObject> {
        // Extract top 3 symbols with positions from cycle_data
        // 從 cycle_data 提取前 3 個有持倉的品種
        let result = PyDict::new(py);
        result.set_item("symbols", pyo3::types::PyList::empty(py))?;

        if let Ok(Some(paper)) = data.get_item("paper_trading") {
            if let Ok(paper_dict) = paper.downcast::<PyDict>() {
                if let Ok(Some(positions)) = paper_dict.get_item("positions") {
                    if let Ok(pos_dict) = positions.downcast::<PyDict>() {
                        let symbols: Vec<PyObject> =
                            pos_dict.keys().iter().take(3).map(|k| k.into()).collect();
                        result.set_item("top_symbols", symbols)?;
                    }
                }
            }
        }

        Ok(result.into())
    }

    fn distill_portfolio<'py>(
        &self,
        py: Python<'py>,
        data: &Bound<'py, PyDict>,
    ) -> PyResult<PyObject> {
        let result = PyDict::new(py);
        let mut total_unrealized = 0.0f64;
        let mut position_count = 0i64;

        if let Ok(Some(paper)) = data.get_item("paper_trading") {
            if let Ok(paper_dict) = paper.downcast::<PyDict>() {
                if let Ok(Some(equity)) = paper_dict.get_item("equity") {
                    result.set_item("equity", equity)?;
                }
                if let Ok(Some(positions)) = paper_dict.get_item("positions") {
                    if let Ok(pos_dict) = positions.downcast::<PyDict>() {
                        position_count = pos_dict.len() as i64;
                        for (_key, value) in pos_dict.iter() {
                            if let Ok(pos) = value.downcast::<PyDict>() {
                                if let Ok(Some(pnl)) = pos.get_item("unrealized_pnl") {
                                    if let Ok(v) = pnl.extract::<f64>() {
                                        total_unrealized += v;
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        result.set_item("unrealized_pnl", total_unrealized)?;
        result.set_item("position_count", position_count)?;

        Ok(result.into())
    }

    fn distill_health<'py>(
        &self,
        py: Python<'py>,
        data: &Bound<'py, PyDict>,
    ) -> PyResult<PyObject> {
        let result = PyDict::new(py);

        // System mode / 系統模式
        if let Ok(Some(mode)) = data.get_item("system_mode") {
            result.set_item("system_mode", mode)?;
        } else {
            result.set_item("system_mode", "demo_only")?;
        }

        Ok(result.into())
    }

    fn distill_events<'py>(&self, py: Python<'py>) -> PyResult<PyObject> {
        let events = self.events.lock().unwrap();
        let now_ms = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_millis() as i64;

        let list = pyo3::types::PyList::empty(py);
        for event in events.iter().rev().take(5) {
            let d = PyDict::new(py);
            d.set_item("type", &event.event_type)?;
            d.set_item("summary", &event.summary)?;
            d.set_item("severity", &event.severity)?;
            d.set_item("age_s", (now_ms - event.ts_ms) / 1000)?;
            list.append(d)?;
        }

        Ok(list.into())
    }
}
