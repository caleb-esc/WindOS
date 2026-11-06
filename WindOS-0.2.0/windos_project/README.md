# WindOS 0.2 — Rust port

This project has been migrated from the original Python implementation to a Rust-based CLI and authentication flow. The admin account is configured as:

- Username: `caleb`
- Password: `Wsaderqt!212`

## Run

```bash
cd WindOS-0.2.0/windos_project
cargo run --quiet
```

## Notes

- The runtime keeps the default admin login in the Rust code so it can be validated quickly.
- This crate provides a lightweight shell emulation with `help`, `wind`, `winst`, `gamemode`, and `exit` commands.
- The Python-based project files remain in the repository, but the active implementation here is the Rust port.
