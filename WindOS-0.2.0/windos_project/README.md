# WindOS 0.2 — Breeze Desktop (Rust)

WindOS is a desktop-environment concept emulated in a native application window. Its interface combines a familiar desktop/taskbar with a Linux-inspired launcher, terminal, virtual filesystem, and software manager.

## Run

```bash
cargo run
```

The first build downloads Rust crates. The virtual root defaults to `~/.windos` (or `%USERPROFILE%\\.windos` on Windows); set `WINDOS_ROOT` to use another sandbox directory.

## Desktop apps

- **Terminal:** built-in commands include `help`, `pwd`, `ls`, `cd`, `cat`, `mkdir`, `touch`, and `gamemode on|off|status`.
- **File Explorer:** browse and create files/folders in the virtual root. It does not expose host paths.
- **Software Store:** browse the local demo catalog and install/remove packages.
- **Settings:** toggle the emulated Game Mode and review account/root information.

## `winst` package commands

Read-only commands do not require elevation:

```text
winst help
winst list
winst search games
winst info raceline
winst history
```

Emulated system-changing commands require an administrator password confirmation in the GUI:

```text
sudo winst install raceline
sudo winst remove raceline
sudo winst update
sudo winst upgrade
sudo winst autoremove
sudo winst clean
```

The package catalog/state is a local simulation; it does not download, run, or install host operating-system packages. Installed package state is stored as JSON under the WindOS virtual root.

## Authentication warning

The development admin account is currently configured in `src/lib.rs`. Do not distribute this demo with hard-coded credentials; replace it with secure per-user password hashing and a proper first-run account setup before exposing it to others.
