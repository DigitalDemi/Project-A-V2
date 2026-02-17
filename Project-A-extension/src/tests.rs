#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::NamedTempFile;

    #[test]
    fn test_append_to_log() {
        let mut temp_file = NamedTempFile::new().unwrap();
        let path = temp_file.path().to_path_buf();
        
        // Append event
        append_to_log(&path, "START THEORY pandas\n").unwrap();
        
        // Read back
        let content = std::fs::read_to_string(&path).unwrap();
        assert!(content.contains("START THEORY pandas"));
    }

    #[test]
    fn test_read_log() {
        let mut temp_file = NamedTempFile::new().unwrap();
        writeln!(temp_file, "START THEORY pandas").unwrap();
        writeln!(temp_file, "START GAME valorant").unwrap();
        writeln!(temp_file, "").unwrap(); // Empty line
        
        let path = temp_file.path().to_path_buf();
        let events = read_log(&path).unwrap();
        
        assert_eq!(events.len(), 2);
        assert_eq!(events[0], "START THEORY pandas");
        assert_eq!(events[1], "START GAME valorant");
    }

    #[test]
    fn test_log_append_only() {
        // Critical invariant: log is append-only
        let mut temp_file = NamedTempFile::new().unwrap();
        let path = temp_file.path().to_path_buf();
        
        // Write initial
        append_to_log(&path, "START THEORY pandas\n").unwrap();
        
        // Append more
        append_to_log(&path, "START PRACTICE rust\n").unwrap();
        
        // Read all
        let content = std::fs::read_to_string(&path).unwrap();
        let lines: Vec<&str> = content.lines().collect();
        
        // Both lines exist, order preserved
        assert_eq!(lines.len(), 2);
        assert_eq!(lines[0], "START THEORY pandas");
        assert_eq!(lines[1], "START PRACTICE rust");
    }
}
