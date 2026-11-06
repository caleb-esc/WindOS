# WindOS

WindOS is a lightweight, gaming-first Linux distribution concept emulated in pure Python using only the standard library. It runs as a simulated operating environment on top of Windows, macOS, or Linux, with a virtual filesystem, user system, package manager, service model, and Windows CMD-compatible shell.

## Features

- Virtual root sandbox under `~/.windos` (or override with `--root` / `WINDOS_ROOT`)
- `winst` package manager with dependency resolution, upgrades, rollback, and package history
- `sudo`-style privilege model for system changes
- Windows-style commands such as `dir`, `cls`, `type`, `copy`, `del`, and `tasklist`
- `wind` hub for quick navigation and app launching
- `gamemode` support for performance tuning while gaming
- Emulated system services and package categories for apps and games
- No external dependencies beyond Python 3

## Project layout

This repository is centered around a single script:

- `windos.py` – the full WindOS emulator, shell, package manager, and boot logic

## Requirements

- Python 3.8+
- A terminal/console that supports normal text output

## Quick start

From the repository root:

```bash
python windos.py
```

On first launch, WindOS will create a virtual filesystem and walk you through initial setup, including:

- hostname
- username
- password
- base system initialization

## Common commands

Once inside the shell, you can use commands like:

```bash
help
wind
winst help
winst search raceline
sudo winst install raceline
run raceline
gamemode on
```

## Useful options

```bash
python windos.py --reset
python windos.py --root /path/to/custom/root
python windos.py -c "help; wind"
```

- `--reset` removes the virtual root and starts over
- `--root` tells WindOS to use a custom virtual root location
- `-c/--command` runs shell commands and exits immediately

## Notes

WindOS is a prototype/emulation layer, not a full Linux distribution. It is designed to feel like a playful, lightweight distro simulation with package management and shell behavior inspired by both Linux and Windows.

## License

This project does not currently include a license file. If you plan to distribute or reuse it publicly, you may want to add an open-source license of your choice.

## Example session

```text
$ python windos.py
Welcome to WindOS 0.1.0 (Breeze). Type 'wind' for the Hub, 'help' for commands.

player@windos:~$ help
player@windos:~$ wind
```

## Contributing

This repository is a single-file prototype. If you want to improve it, a good place to start is by editing `windos.py` and keeping the existing command behavior consistent with the project’s playful, simulated OS style.
