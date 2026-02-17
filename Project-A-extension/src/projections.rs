use std::path::PathBuf;
use std::io::BufRead;
use serde::Serialize;
use crate::models::{Session, QueryResult};

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::NamedTempFile;

    #[test]
    fn test_session_projector_basic() {
        let mut temp_file = NamedTempFile::new().unwrap();
        writeln!(temp_file, "START THEORY pandas").unwrap();
        writeln!(temp_file, "START GAME valorant").unwrap();
        writeln!(temp_file, "START PRACTICE rust").unwrap();
        
        let projector = SessionProjector::new(&temp_file.path().to_path_buf());
        let sessions = projector.get_all_sessions();
        
        assert_eq!(sessions.len(), 3);
        assert_eq!(sessions[0].category, "THEORY");
        assert_eq!(sessions[1].category, "GAME");
        assert_eq!(sessions[2].category, "PRACTICE");
    }

    #[test]
    fn test_session_boundaries() {
        // Test: session ends when new start occurs
        let mut temp_file = NamedTempFile::new().unwrap();
        writeln!(temp_file, "START THEORY pandas").unwrap();  // Session 1 start
        writeln!(temp_file, "START GAME valorant").unwrap();   // Session 1 end, Session 2 start
        
        let projector = SessionProjector::new(&temp_file.path().to_path_buf());
        let sessions = projector.get_all_sessions();
        
        assert_eq!(sessions.len(), 2);
        assert_eq!(sessions[0].end_event_idx, Some(0));  // Ends at index 0
        assert_eq!(sessions[1].start_event_idx, 1);       // Starts at index 1
    }

    #[test]
    fn test_activity_recurrence() {
        // Test: same activity can have multiple sessions
        let mut temp_file = NamedTempFile::new().unwrap();
        writeln!(temp_file, "START THEORY pandas").unwrap();
        writeln!(temp_file, "START GAME valorant").unwrap();
        writeln!(temp_file, "START THEORY pandas").unwrap();  // Same activity, new session
        
        let projector = SessionProjector::new(&temp_file.path().to_path_buf());
        let sessions = projector.get_all_sessions();
        
        assert_eq!(sessions.len(), 3);
        
        let theory_sessions: Vec<_> = sessions.iter()
            .filter(|s| s.category == "THEORY")
            .collect();
        assert_eq!(theory_sessions.len(), 2);
    }

    #[test]
    fn test_ratio_analyzer() {
        let mut temp_file = NamedTempFile::new().unwrap();
        writeln!(temp_file, "START THEORY pandas").unwrap();
        writeln!(temp_file, "START THEORY rust").unwrap();
        writeln!(temp_file, "START PRACTICE python").unwrap();
        writeln!(temp_file, "START GAME valorant").unwrap();
        
        let analyzer = RatioAnalyzer::new(&temp_file.path().to_path_buf());
        let result = analyzer.analyze();
        
        assert_eq!(result.result_type, "analysis");
        
        // Parse the data
        let analysis: RatioAnalysis = serde_json::from_value(result.data).unwrap();
        assert_eq!(analysis.total_events, 4);
        
        // Check categories
        let theory_count = analysis.categories.iter()
            .find(|c| c.category == "THEORY")
            .map(|c| c.count)
            .unwrap_or(0);
        assert_eq!(theory_count, 2);
    }

    #[test]
    fn test_no_stop_events_needed() {
        // Test: sessions derived without explicit STOP
        let mut temp_file = NamedTempFile::new().unwrap();
        writeln!(temp_file, "START THEORY pandas").unwrap();
        writeln!(temp_file, "START PRACTICE rust").unwrap();
        // No STOP event, but should still work
        
        let projector = SessionProjector::new(&temp_file.path().to_path_buf());
        let sessions = projector.get_all_sessions();
        
        assert_eq!(sessions.len(), 2);
        assert!(sessions[0].end_event_idx.is_some());
    }
}

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
