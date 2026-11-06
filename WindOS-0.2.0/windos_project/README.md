# WindOS 0.2 — Breeze Desktop

WindOS is a Python-based operating-system emulation project. It runs in a sandboxed virtual root on the host OS; it is **not** a bootable operating-system distribution.

## Project layout

```text
windos-project/
├── windos/
│   ├── core/
│   │   ├── engine.py       # Existing WindOS shell, virtual filesystem, services, winst
│   │   └── auth.py         # Shared PBKDF2 password verification
│   ├── desktop/
│   │   └── app.py          # PySide6 desktop: login, terminal, files, system panel
│   ├── web/
│   │   └── app.py          # Authenticated localhost browser gateway
│   ├── cli.py              # CLI entry point / first boot
│   └── __init__.py
├── tests/
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Install

Python 3.10+ is recommended.

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\\Scripts\\activate
pip install -e ".[all]"
```

## First boot and CLI

```bash
python -m windos.cli
```

The first run creates a WindOS user in the virtual root (`~/.windos` by default). Existing password hashes and account data are retained in that root. To use a different root, set `WINDOS_ROOT` before starting the app.

## Desktop environment

```bash
python -m windos.desktop.app
```

Sign in using the same WindOS username and password created during CLI first boot. The desktop includes a command terminal, virtual filesystem browser, system overview, and Game Mode toggle.

A graphical PySide6 desktop requires a graphical display. GitHub Codespaces / github.dev browser tabs do not provide a normal desktop display server; run the PySide6 app on a machine with a GUI or use a remote desktop solution such as VNC in a Codespace.

## Localhost browser gateway

```bash
python -m windos.web.app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`. Sign in with the same WindOS account. This gateway provides a browser terminal connected to the same WindOS engine and virtual root. The web gateway blocks direct host-shell commands (`host`, `exit`, `reboot`, etc.); it is not intended to expose the host operating system.

### GitHub Codespaces port forwarding

Run the web gateway **inside a GitHub Codespace** on port `8000`. In the Codespaces **Ports** panel, set port 8000 visibility to **Private** (recommended), then open the forwarded URL. Codespaces normally creates a URL shaped like:

```text
https://<codespace-name>-8000.app.github.dev
```

`github.dev` (the browser-based VS Code editor at github.dev) is not itself a runtime and does not host a Python server. The forwarded application URL is provided by **GitHub Codespaces**, not by the github.dev editor URL.

## Security notes

- Passwords are verified using the existing PBKDF2-HMAC-SHA256 hash and per-user salt. Plaintext passwords are not stored.
- Do not expose the gateway publicly. Keep the Codespaces port private and use a strong WindOS password.
- The browser gateway keeps sessions in memory and uses an HttpOnly, SameSite cookie. Restarting the server signs everyone out.
- The legacy CLI engine includes a `host` command for local interactive use. The web gateway explicitly blocks it because remote host-command execution is unsafe.
- WindOS's users, packages, and filesystem remain an emulated environment under the virtual root, not real host accounts or system packages.
