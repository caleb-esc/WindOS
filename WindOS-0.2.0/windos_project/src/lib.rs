use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, fs, path::PathBuf};

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
        Self { username: ADMIN_USERNAME.into(), groups: vec!["admin".into(), "users".into()], home: "/home/caleb".into() }
    }
}

pub fn default_user() -> UserRecord { UserRecord::default() }
pub fn authenticate(username: &str, password: &str) -> bool {
    username == ADMIN_USERNAME && password == ADMIN_PASSWORD
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Package {
    pub name: String,
    pub version: String,
    pub description: String,
    pub category: String,
    pub size_kb: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PackageState {
    pub installed: BTreeMap<String, String>,
    pub history: Vec<String>,
    pub revision: u32,
}

impl Default for PackageState {
    fn default() -> Self {
        Self { installed: BTreeMap::new(), history: Vec::new(), revision: 1 }
    }
}

pub fn catalog() -> Vec<Package> {
    vec![
        Package { name:"winpad".into(), version:"1.0.3".into(), description:"Fast text editor".into(), category:"Apps".into(), size_kb:900 },
        Package { name:"windbrowse".into(), version:"4.1.0".into(), description:"Lightweight web browser".into(), category:"Apps".into(), size_kb:21000 },
        Package { name:"windplay".into(), version:"2.2.0".into(), description:"Media player".into(), category:"Apps".into(), size_kb:4200 },
        Package { name:"fpsmeter".into(), version:"0.5.0".into(), description:"FPS and frametime overlay".into(), category:"Tools".into(), size_kb:700 },
        Package { name:"pixelquest".into(), version:"1.0.0".into(), description:"2D pixel adventure".into(), category:"Games".into(), size_kb:9000 },
        Package { name:"stackblocks".into(), version:"3.1.0".into(), description:"Falling-block puzzle".into(), category:"Games".into(), size_kb:2500 },
        Package { name:"raceline".into(), version:"1.2.0".into(), description:"Arcade racer".into(), category:"Games".into(), size_kb:42000 },
        Package { name:"voidstrike".into(), version:"2.0.0".into(), description:"Space shooter".into(), category:"Games".into(), size_kb:65000 },
        Package { name:"libwindgl".into(), version:"1.4.0".into(), description:"Lightweight graphics layer".into(), category:"System".into(), size_kb:5200 },
    ]
}

fn state_path() -> PathBuf {
    std::env::var_os("WINDOS_ROOT").map(PathBuf::from)
        .or_else(|| std::env::var_os("USERPROFILE").map(|p| PathBuf::from(p).join(".windos")))
        .or_else(|| std::env::var_os("HOME").map(|p| PathBuf::from(p).join(".windos")))
        .unwrap_or_else(|| PathBuf::from(".windos"))
        .join("var/lib/winst/rust-state.json")
}

pub fn load_package_state() -> PackageState {
    fs::read(state_path()).ok().and_then(|b| serde_json::from_slice(&b).ok()).unwrap_or_default()
}

pub fn save_package_state(state: &PackageState) -> Result<(), String> {
    let path = state_path();
    if let Some(parent) = path.parent() { fs::create_dir_all(parent).map_err(|e| e.to_string())?; }
    let bytes = serde_json::to_vec_pretty(state).map_err(|e| e.to_string())?;
    let tmp = path.with_extension("json.tmp");
    fs::write(&tmp, bytes).map_err(|e| e.to_string())?;
    fs::rename(tmp, path).map_err(|e| e.to_string())
}

pub fn install_package(state: &mut PackageState, name: &str) -> Result<String, String> {
    let package = catalog().into_iter().find(|p| p.name == name).ok_or_else(|| format!("unable to locate package '{name}'"))?;
    if state.installed.contains_key(name) { return Ok(format!("{name} is already installed ({})", state.installed[name])); }
    state.installed.insert(name.into(), package.version.clone());
    state.history.push(format!("installed {name} {}", package.version));
    save_package_state(state)?;
    Ok(format!("Installed {} {} ({} kB)", package.name, package.version, package.size_kb))
}

pub fn remove_package(state: &mut PackageState, name: &str) -> Result<String, String> {
    let version = state.installed.remove(name).ok_or_else(|| format!("package '{name}' is not installed"))?;
    state.history.push(format!("removed {name} {version}"));
    save_package_state(state)?;
    Ok(format!("Removed {name} {version}"))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn admin_login_works() { assert!(authenticate("caleb", "Wsaderqt!212")); }
    #[test] fn bad_credentials_fail() { assert!(!authenticate("caleb", "wrong")); assert!(!authenticate("root", ADMIN_PASSWORD)); }
}
