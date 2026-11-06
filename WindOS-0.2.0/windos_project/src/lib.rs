use serde::{Deserialize, Serialize};

pub const ADMIN_USERNAME: &str = "caleb";
pub const ADMIN_PASSWORD: &str = "Wsaderqt!212";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct UserRecord {
    pub username: String,
    pub groups: Vec<String>,
    pub home: String,
}

impl Default for UserRecord {
    fn default() -> Self {
        Self {
            username: ADMIN_USERNAME.to_string(),
            groups: vec!["admin".to_string(), "users".to_string()],
            home: "/home/caleb".to_string(),
        }
    }
}

pub fn default_user() -> UserRecord {
    UserRecord::default()
}

pub fn authenticate(username: &str, password: &str) -> bool {
    username == ADMIN_USERNAME && password == ADMIN_PASSWORD
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn admin_credentials_are_accepted() {
        assert!(authenticate("caleb", "Wsaderqt!212"));
    }

    #[test]
    fn invalid_credentials_are_rejected() {
        assert!(!authenticate("caleb", "wrong-password"));
        assert!(!authenticate("admin", "Wsaderqt!212"));
    }
}
