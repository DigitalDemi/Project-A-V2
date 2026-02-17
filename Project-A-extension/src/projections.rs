use std::path::PathBuf;
use std::io::BufRead;
use serde::Serialize;
use crate::models::{Session, QueryResult};

/// Projects sessions from event log
/// Session = period between START events
pub struct SessionProjector {
    log_path: PathBuf,
}

impl SessionProjector {
    pub fn new(log_path: &PathBuf) -> Self {
        Self {
            log_path: log_path.clone(),
        }
    }

    fn read_events(&self) -> Vec<String> {
        match std::fs::File::open(&self.log_path) {
            Ok(file) => {
                let reader = std::io::BufReader::new(file);
                reader.lines()
                    .filter_map(|line| line.ok())
                    .filter(|line| !line.trim().is_empty())
                    .collect()
            }
            Err(_) => Vec::new(),
        }
    }

    pub fn get_all_sessions(&self) -> Vec<Session> {
        let events = self.read_events();
        let mut sessions = Vec::new();
        let mut current_session: Option<Session> = None;

        for (idx, line) in events.iter().enumerate() {
            let parts: Vec<&str> = line.split_whitespace().collect();
            
            if parts.len() >= 3 && parts[0] == "START" {
                // End previous session
                if let Some(mut session) = current_session.take() {
                    session.end_event_idx = Some(idx - 1);
                    session.is_active = false;
                    sessions.push(session);
                }

                // Start new session
                current_session = Some(Session {
                    category: parts[1].to_string(),
                    activity: parts[2].to_string(),
                    start_event_idx: idx,
                    end_event_idx: None,
                    is_active: true,
                });
            }
        }

        // Don't forget the last session
        if let Some(session) = current_session {
            sessions.push(session);
        }

        sessions
    }

    pub fn get_current_session(&self) -> Option<Session> {
        let sessions = self.get_all_sessions();
        sessions.into_iter().find(|s| s.is_active)
    }

    pub fn get_timeline(&self) -> QueryResult {
        let sessions = self.get_all_sessions();
        
        QueryResult {
            query: "timeline".to_string(),
            result_type: "sessions".to_string(),
            data: serde_json::json!({
                "sessions": sessions,
                "total": sessions.len(),
                "active": sessions.iter().filter(|s| s.is_active).count(),
            }),
        }
    }
}

/// Analyzes ratios between activity types
pub struct RatioAnalyzer {
    log_path: PathBuf,
}

#[derive(Debug, Serialize)]
pub struct RatioAnalysis {
    pub categories: Vec<CategoryCount>,
    pub total_events: usize,
    pub theory_to_practice: f64,
}

#[derive(Debug, Serialize)]
pub struct CategoryCount {
    pub category: String,
    pub count: usize,
    pub percentage: f64,
}

impl RatioAnalyzer {
    pub fn new(log_path: &PathBuf) -> Self {
        Self {
            log_path: log_path.clone(),
        }
    }

    fn read_events(&self) -> Vec<String> {
        match std::fs::File::open(&self.log_path) {
            Ok(file) => {
                let reader = std::io::BufReader::new(file);
                reader.lines()
                    .filter_map(|line| line.ok())
                    .filter(|line| !line.trim().is_empty())
                    .collect()
            }
            Err(_) => Vec::new(),
        }
    }

    pub fn analyze(&self) -> QueryResult {
        let events = self.read_events();
        let mut counts: std::collections::HashMap<String, usize> = std::collections::HashMap::new();

        for line in &events {
            let parts: Vec<&str> = line.split_whitespace().collect();
            if parts.len() >= 2 {
                let category = parts[1].to_string();
                *counts.entry(category).or_insert(0) += 1;
            }
        }

        let total: usize = counts.values().sum();
        
        let mut categories: Vec<CategoryCount> = counts
            .into_iter()
            .map(|(cat, count)| CategoryCount {
                category: cat.clone(),
                count,
                percentage: if total > 0 { (count as f64 / total as f64) * 100.0 } else { 0.0 },
            })
            .collect();
        
        categories.sort_by(|a, b| b.count.cmp(&a.count));

        let theory_count = categories.iter().find(|c| c.category == "THEORY").map(|c| c.count).unwrap_or(0);
        let practice_count = categories.iter().find(|c| c.category == "PRACTICE").map(|c| c.count).unwrap_or(1);

        let analysis = RatioAnalysis {
            categories,
            total_events: total,
            theory_to_practice: theory_count as f64 / practice_count as f64,
        };

        QueryResult {
            query: "ratios".to_string(),
            result_type: "analysis".to_string(),
            data: serde_json::to_value(analysis).unwrap_or_default(),
        }
    }
}
