use axum::{
    routing::{get, post},
    Router,
    Json,
    http::StatusCode,
};
use serde::{Deserialize, Serialize};
use std::net::SocketAddr;
use std::fs::OpenOptions;
use std::io::Write;
use std::path::PathBuf;
use chrono::Utc;

mod models;
mod projections;

use models::{Event, EventInput, ApiResponse, QueryResult};
use projections::{SessionProjector, RatioAnalyzer};

/// Event-driven HTTP API
/// Never edits master.log, only appends
/// All state derived from event log
#[derive(Clone)]
struct AppState {
    log_path: PathBuf,
}

#[tokio::main]
async fn main() {
    // Initialize state
    let state = AppState {
        log_path: PathBuf::from("../Project-A/log/master.log"),
    };

    // Build router
    let app = Router::new()
        .route("/", get(root))
        .route("/health", get(health_check))
        .route("/events", post(create_event))
        .route("/events", get(list_events))
        .route("/query", post(handle_query))
        .route("/projections/sessions", get(get_sessions))
        .route("/projections/ratios", get(get_ratios))
        .with_state(state);

    // Run server
    let addr = SocketAddr::from(([127, 0, 0, 1], 8080));
    println!("🚀 Server running on http://{}", addr);
    
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}

async fn root() -> &'static str {
    "Event-Driven Agent API v0.1.0"
}

async fn health_check() -> Json<serde_json::Value> {
    Json(serde_json::json!({
        "status": "healthy",
        "timestamp": Utc::now().to_rfc3339(),
    }))
}

/// Create a new event
/// Appends to master.log (append-only, never edit)
async fn create_event(
    state: axum::extract::State<AppState>,
    Json(input): Json<EventInput>,
) -> Result<Json<ApiResponse>, StatusCode> {
    
    // Validate event format
    let event_line = format!("{}\n", input.event.trim());
    
    // Append to master.log (the only write operation allowed)
    match append_to_log(&state.log_path, &event_line) {
        Ok(_) => {
            // Derive session info
            let projector = SessionProjector::new(&state.log_path);
            let current_session = projector.get_current_session();
            
            Ok(Json(ApiResponse {
                status: "success".to_string(),
                message: format!("Event logged: {}", input.event),
                data: Some(serde_json::json!({
                    "event": input.event,
                    "timestamp": Utc::now().to_rfc3339(),
                    "session_info": current_session,
                })),
            }))
        }
        Err(e) => {
            eprintln!("Error writing to log: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// List all events (read-only)
async fn list_events(
    state: axum::extract::State<AppState>,
) -> Result<Json<Vec<String>>, StatusCode> {
    match read_log(&state.log_path) {
        Ok(events) => Ok(Json(events)),
        Err(e) => {
            eprintln!("Error reading log: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// Handle complex queries
async fn handle_query(
    state: axum::extract::State<AppState>,
    Json(query): Json<serde_json::Value>,
) -> Result<Json<QueryResult>, StatusCode> {
    
    let query_str = query.get("query")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    
    // Route to appropriate projector
    let result = if query_str.contains("ratio") {
        let analyzer = RatioAnalyzer::new(&state.log_path);
        analyzer.analyze()
    } else if query_str.contains("session") || query_str.contains("timeline") {
        let projector = SessionProjector::new(&state.log_path);
        projector.get_timeline()
    } else {
        // Default: return recent events
        match read_log(&state.log_path) {
            Ok(events) => QueryResult {
                query: query_str.to_string(),
                result_type: "recent".to_string(),
                data: serde_json::json!({ "events": events }),
            },
            Err(e) => {
                eprintln!("Error: {}", e);
                return Err(StatusCode::INTERNAL_SERVER_ERROR);
            }
        }
    };
    
    Ok(Json(result))
}

/// Get session projections
async fn get_sessions(
    state: axum::extract::State<AppState>,
) -> Result<Json<serde_json::Value>, StatusCode> {
    let projector = SessionProjector::new(&state.log_path);
    let sessions = projector.get_all_sessions();
    
    Ok(Json(serde_json::json!({
        "sessions": sessions,
        "count": sessions.len(),
    })))
}

/// Get ratio projections
async fn get_ratios(
    state: axum::extract::State<AppState>,
) -> Result<Json<serde_json::Value>, StatusCode> {
    let analyzer = RatioAnalyzer::new(&state.log_path);
    let analysis = analyzer.analyze();
    
    Ok(Json(serde_json::json!({
        "analysis": analysis,
    })))
}

// Helper functions

fn append_to_log(path: &PathBuf, line: &str) -> std::io::Result<()> {
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)?;
    
    file.write_all(line.as_bytes())?;
    Ok(())
}

fn read_log(path: &PathBuf) -> std::io::Result<Vec<String>> {
    use std::io::BufRead;
    
    let file = std::fs::File::open(path)?;
    let reader = std::io::BufReader::new(file);
    
    let mut events = Vec::new();
    for line in reader.lines() {
        if let Ok(line) = line {
            if !line.trim().is_empty() {
                events.push(line);
            }
        }
    }
    
    Ok(events)
}
