# WindOS 0.2 — Breeze Desktop (Rust)

WindOS is a desktop-environment concept emulated in a native application window. Its interface blends a Windows-like launcher and taskbar with a Linux-inspired sidebar, terminal, and system controls. This is a desktop simulation, not a bootable operating system.

## Run

Install a current Rust toolchain, then from this directory run:

```bash
cargo run
```

The first build downloads the Rust crates. On Linux, the windowing backend may require system development packages such as X11/Wayland and OpenGL libraries, depending on your distribution.

## Desktop features

- Sign-in screen and a dark “Midnight Breeze” theme
- Launcher sidebar, pinned apps, taskbar, and status panel
- Windowed terminal with basic WindOS demo commands
- Virtual home-directory file browser and settings window
- Toggleable emulated Game Mode

The default admin account is configured in `src/lib.rs` as `caleb`. The password is a development default; change it before sharing or exposing the application. This demo currently authenticates against that configured credential and does not provide production account storage.
