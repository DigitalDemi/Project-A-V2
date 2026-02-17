use serde::{Deserialize, Serialize};

/// Event input from API
#[derive(Debug, Deserialize)]
pub struct EventInput {
    pub event: String,
}

/// Event structure (minimal, as per architecture)
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Event {
    pub line: String,
    pub timestamp: String,
}

/// API Response
#[derive(Debug, Serialize)]
pub struct ApiResponse {
    pub status: String,
    pub message: String,
    pub data: Option<serde_json::Value>,
}

/// Query result
#[derive(Debug, Serialize)]
pub struct QueryResult {
    pub query: String,
    pub result_type: String,
    pub data: serde_json::Value,
}

/// Session projection (derived from events)
#[derive(Debug, Serialize, Clone)]
pub struct Session {
    pub category: String,
    pub activity: String,
    pub start_event_idx: usize,
    pub end_event_idx: Option<usize>,
    pub is_active: bool,
}

/// Activity statistics
#[derive(Debug, Serialize)]
pub struct ActivityStats {
    pub category: String,
    pub count: usize,
    pub percentage: f64,
}
