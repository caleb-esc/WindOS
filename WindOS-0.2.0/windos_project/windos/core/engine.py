#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WindOS 0.1 "Breeze" - emulation layer prototype
================================================
A lightweight, gaming-first Linux distro concept, emulated in pure Python
(stdlib only) on top of Windows, macOS or Linux.

  * Sandboxed virtual root (default ~/.windos, override with --root or $WINDOS_ROOT)
  * winst  - the WindOS package manager (dependency resolver, conflicts,
             transactions with rollback, history/undo, upgrades, extra sources)
  * sudo   - privilege model. System changes (winst install/remove/update...)
             need `sudo`, exactly like a real distro
  * Windows CMD commands work natively (dir, cls, type, copy, del, tasklist...)
  * gamemode - one command to strip background services and boost game FPS
  * wind   - the Hub: one-key navigation + type-to-search, easier than Mint's menu

Run:   python windos.py
Help:  type `help` inside WindOS, or `winst help`
"""
import argparse
import contextlib
import datetime
import difflib
import getpass
import hashlib
import io
import json
import os
import platform
import random
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

VERSION = "0.2.0"
CODENAME = "Breeze"
SUDO_TTL = 300  # seconds sudo stays unlocked
FAST = bool(os.environ.get("WINDOS_FAST"))

# --------------------------------------------------------------------------
# Terminal helpers
# --------------------------------------------------------------------------
if os.name == "nt":
    os.system("")  # enable ANSI escapes on Windows 10+
with contextlib.suppress(Exception):
    sys.stdout.reconfigure(encoding="utf-8")
USE_COLOR = sys.stdout.isatty()


def _c(code):
    return lambda t: f"\033[{code}m{t}\033[0m" if USE_COLOR else str(t)


green, red, yellow, cyan, bold, dim, magenta = (
    _c("32"), _c("31"), _c("33"), _c("36"), _c("1"), _c("2"), _c("35"))


def sleep(t):
    if not FAST:
        time.sleep(t)


def fmt_kb(kb):
    return f"{kb / 1024:.1f} MB" if kb >= 1024 else f"{kb} kB"


def confirm(msg):
    try:
        return input(msg).strip().lower() in ("", "y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def ask_password(prompt):
    if "WINDOS_PASS" in os.environ:
        return os.environ["WINDOS_PASS"]
    try:
        return getpass.getpass(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def prompt(msg, default=""):
    try:
        v = input(msg).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        v = ""
    return v or default


# --------------------------------------------------------------------------
# Virtual filesystem layout
# --------------------------------------------------------------------------
ROOT = Path.home() / ".windos"


def set_root(p):
    global ROOT, USERS_F, CONFIG_F, SERVICES_F, SOURCES_F, INDEX_F
    global INSTALLED_F, HISTORY_F, LOCK_F, CACHE_D, AUTH_LOG
    ROOT = Path(p).expanduser().resolve()
    USERS_F = ROOT / "etc/windos/users.json"
    CONFIG_F = ROOT / "etc/windos/windos.json"
    SERVICES_F = ROOT / "etc/windos/services.json"
    SOURCES_F = ROOT / "etc/winst/sources.json"
    INDEX_F = ROOT / "var/lib/winst/index.json"
    INSTALLED_F = ROOT / "var/lib/winst/installed.json"
    HISTORY_F = ROOT / "var/lib/winst/history.json"
    LOCK_F = ROOT / "var/lib/winst/lock"
    CACHE_D = ROOT / "var/cache/winst"
    AUTH_LOG = ROOT / "var/log/auth.log"


set_root(os.environ.get("WINDOS_ROOT", ROOT))
PROTECTED_USERS_FILE = "/etc/windos/users.json"
DIRS = ["etc/windos", "etc/winst", "var/lib/winst", "var/log", "var/cache/winst",
        "usr/bin", "usr/share/applications", "usr/share/winst", "opt/games", "home", "tmp"]


def jload(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def jsave(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def hpath(v):
    """virtual path -> host path"""
    return ROOT if v == "/" else ROOT.joinpath(*v.strip("/").split("/"))


def hash_pw(pw, salt=None):
    salt = salt or secrets.token_hex(8)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 120_000).hex()
    return salt, h


def log_auth(msg):
    AUTH_LOG.parent.mkdir(parents=True, exist_ok=True)
    with AUTH_LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")


# --------------------------------------------------------------------------
# The official repository (stable mirror, emulated)
# --------------------------------------------------------------------------
def pk(ver, desc, cat, deps=(), size=800, conflicts=(), kind="lib", fps=0):
    return dict(version=ver, desc=desc, category=cat, deps=list(deps), size_kb=size,
                conflicts=list(conflicts), kind=kind, fps=fps)


BASE_REPO = {
    "libc-wind": pk("1.0.0", "Core C runtime", "libs", size=2400),
    "libwindgl": pk("1.4.0", "Lightweight OpenGL layer", "libs", ["libc-wind"], 5200),
    "libvulkan-lite": pk("1.0.0", "Slim Vulkan driver stack", "libs", ["libc-wind"], 7800),
    "libaudio-lite": pk("0.9.2", "Low-latency audio stack", "libs", ["libc-wind"], 1900),
    "libinput-fast": pk("2.0.0", "1000Hz input polling", "libs", ["libc-wind"], 600),
    "wind-compositor-lite": pk("1.1.0", "Tiny zero-copy compositor", "system", ["libwindgl"],
                               1500, ["heavy-compositor"]),
    "heavy-compositor": pk("3.2.0", "Full-effects compositor (eye candy, slower)", "system",
                           ["libwindgl"], 18000, ["wind-compositor-lite"]),
    "winpad": pk("1.0.3", "Fast text editor", "apps", ["libc-wind"], 900, kind="app"),
    "windbrowse": pk("4.1.0", "Lightweight web browser", "apps", ["libwindgl", "libaudio-lite"],
                     21000, kind="app"),
    "windplay": pk("2.2.0", "Media player", "apps", ["libaudio-lite", "libwindgl"], 4200, kind="app"),
    "fpsmeter": pk("0.5.0", "FPS and frametime overlay", "tools", ["libvulkan-lite"], 700, kind="app"),
    "proton-wind": pk("0.9.4", "Run Windows .exe games natively", "tools",
                      ["libvulkan-lite", "libc-wind"], 34000, kind="app"),
    "pixelquest": pk("1.0.0", "2D pixel adventure", "games", ["libwindgl", "libaudio-lite"],
                     9000, kind="game", fps=240),
    "stackblocks": pk("3.1.0", "Falling-block puzzle", "games", ["libwindgl"], 2500, kind="game", fps=300),
    "raceline": pk("1.2.0", "Arcade racer", "games", ["libvulkan-lite", "libinput-fast"],
                   42000, kind="game", fps=144),
    "voidstrike": pk("2.0.0", "Space shooter", "games",
                     ["libvulkan-lite", "libaudio-lite", "libinput-fast"], 65000, kind="game", fps=120),
    "ironfront": pk("0.8.0", "3D tactical shooter", "games",
                    ["libvulkan-lite", "libinput-fast", "libaudio-lite"], 88000, kind="game", fps=90),
}
# each "revision" is a new state of the mirror; `winst update` pulls the next one
REVISIONS = {
    2: {"raceline": "1.3.0", "libvulkan-lite": "1.1.0"},
    3: {"voidstrike": "2.1.0", "windbrowse": "4.2.1", "proton-wind": "0.9.5"},
}
BASE_SYSTEM = {"libc-wind": "auto", "libwindgl": "auto", "wind-compositor-lite": "manual",
               "libaudio-lite": "manual", "libinput-fast": "manual", "winpad": "manual"}
PROTECTED_PKGS = {"libc-wind"}


def build_base(rev):
    repo = json.loads(json.dumps(BASE_REPO))
    for r in sorted(REVISIONS):
        if r <= rev:
            for n, v in REVISIONS[r].items():
                repo[n]["version"] = v
    return repo


def norm_pkg(d):
    if "version" not in d:
        raise ValueError("package without version")
    base = pk(d["version"], d.get("desc", "(no description)"), d.get("category", "apps"))
    base.update({k: d[k] for k in ("deps", "size_kb", "conflicts", "kind", "fps", "sha256") if k in d})
    return base


def vkey(v):
    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.\-]", v))


def payload_of(name, ver):
    return f"WINDPKG::{name}={ver}".encode()


def sha_of(name, meta):
    return meta.get("sha256") or hashlib.sha256(payload_of(name, meta["version"])).hexdigest()


# --------------------------------------------------------------------------
# winst - package manager
# --------------------------------------------------------------------------
class WinstError(Exception):
    pass


WINST_HELP = """winst - the WindOS package manager

  Query (no sudo):
    winst search <term>            search names, descriptions, categories
    winst list [--installed|--upgradable]
    winst info <pkg>               details, dependencies, reverse dependencies
    winst history                  past transactions
    winst check                    verify files of installed packages
    winst owns <file>              which package owns a file
    winst source list

  Change the system (needs sudo):
    sudo winst install <pkg...>    install with dependencies
    sudo winst remove  <pkg...>    [--purge] [--cascade]
    sudo winst purge   <pkg...>    remove + delete config
    sudo winst update              refresh package index (and extra sources)
    sudo winst upgrade             upgrade everything upgradable
    sudo winst autoremove          remove unneeded auto-installed packages
    sudo winst clean               empty the download cache
    sudo winst undo                revert the last install/remove
    sudo winst source add|remove <url>

  Flags: -y/--yes (no prompt)   -s/--dry-run (simulate only)"""

ROOT_CMDS = {"install", "remove", "purge", "update", "upgrade", "autoremove", "clean", "undo"}


@contextlib.contextmanager
def lock():
    LOCK_F.parent.mkdir(parents=True, exist_ok=True)
    if LOCK_F.exists() and time.time() - LOCK_F.stat().st_mtime > 600:
        LOCK_F.unlink()
    try:
        fd = os.open(str(LOCK_F), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise WinstError("could not get lock /var/lib/winst/lock - another winst is running")
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        LOCK_F.unlink(missing_ok=True)


def progress(label, size_kb):
    n = 24
    for i in range(n + 1):
        sys.stdout.write(f"\r  {label:<26} [{green('#' * i)}{'-' * (n - i)}] {int(i / n * 100):3d}%")
        sys.stdout.flush()
        sleep(0.01)
    sys.stdout.write(f"  {fmt_kb(size_kb)}\n")


def write_pkg(name, meta):
    """Lay package files into the virtual root. Returns (files, conf)."""
    files, conf = [], []

    def w(v, text, is_conf=False):
        p = hpath(v)
        p.parent.mkdir(parents=True, exist_ok=True)
        if not (is_conf and p.exists()):
            p.write_text(text, encoding="utf-8")
        (conf if is_conf else files).append(v)

    ver, kind = meta["version"], meta["kind"]
    w(f"/usr/bin/{name}", f"#!/usr/bin/env windos-run\n# {name} {ver}\n")
    w(f"/usr/share/winst/{name}/manifest.json", json.dumps(
        {"name": name, "version": ver, "kind": kind, "category": meta["category"]}, indent=2))
    if kind in ("game", "app"):
        w(f"/usr/share/applications/{name}.app.json", json.dumps(
            {"name": name, "desc": meta["desc"], "category": meta["category"], "kind": kind}))
        w(f"/etc/{name}.conf", f"# configuration for {name}\nfullscreen=true\nvsync=false\n", True)
    if kind == "game":
        w(f"/opt/games/{name}/game.dat", "WINDGAME\n" + "0" * 64)
    return files, conf


def erase_pkg(name, rec, purge=False):
    targets = list(rec.get("files", [])) + (list(rec.get("conf", [])) if purge else [])
    for v in targets:
        with contextlib.suppress(OSError):
            hpath(v).unlink()
    for d in (f"/usr/share/winst/{name}", f"/opt/games/{name}"):
        with contextlib.suppress(OSError):
            hpath(d).rmdir()


def resolve(requested, pkgs, installed):
    """Dependency resolver: topological order, cycle + conflict detection."""
    plan, seen, stack = [], set(), []

    def visit(name, top):
        if name in stack:
            raise WinstError("dependency cycle: " + " -> ".join(stack + [name]))
        meta = pkgs.get(name)
        if meta is None:
            raise WinstError(f"unable to locate package '{name}'")
        rec = installed.get(name)
        if rec and (not top or vkey(rec["version"]) >= vkey(meta["version"])):
            return
        if name in seen:
            return
        stack.append(name)
        for d in meta["deps"]:
            visit(d, False)
        stack.pop()
        seen.add(name)
        plan.append(name)

    for r in requested:
        visit(r, True)
    final = set(installed) | set(plan)
    for n in final:
        for cf in (pkgs.get(n) or {}).get("conflicts", []):
            if cf in final:
                raise WinstError(f"{n} conflicts with {cf}. Remove one first "
                                 f"(sudo winst remove {cf})")
    return plan


class Winst:
    def __init__(self, sh=None):
        self.sh = sh

    # ---- state -----------------------------------------------------------
    def refresh(self):
        idx = jload(INDEX_F, {"revision": 1, "custom": {}})
        self.rev, self.custom = idx.get("revision", 1), idx.get("custom", {})
        self.pkgs = build_base(self.rev)
        for src_pkgs in self.custom.values():
            self.pkgs.update(src_pkgs)
        self.installed = jload(INSTALLED_F, {})

    def save_installed(self):
        jsave(INSTALLED_F, self.installed)

    def bootstrap(self):
        """Pre-install the base system (first boot)."""
        jsave(INDEX_F, {"revision": 1, "custom": {}})
        self.refresh()
        for n, reason in BASE_SYSTEM.items():
            self.install_record(n, reason)
        self.save_installed()

    def install_record(self, name, reason, meta=None):
        meta = meta or self.pkgs[name]
        files, conf = write_pkg(name, meta)
        self.installed[name] = dict(
            version=meta["version"], reason=reason, deps=meta["deps"], kind=meta["kind"],
            category=meta["category"], desc=meta["desc"], files=files, conf=conf,
            installed_at=datetime.datetime.now().isoformat(timespec="seconds"))

    def upgradable(self):
        return sorted(n for n, r in self.installed.items()
                      if n in self.pkgs and vkey(self.pkgs[n]["version"]) > vkey(r["version"]))

    def unknown(self, name):
        msg = f"unable to locate package '{name}'"
        sug = difflib.get_close_matches(name, list(self.pkgs), n=3, cutoff=0.5)
        return msg + (f". Did you mean: {', '.join(sug)}?" if sug else "")

    def log_history(self, action, **kw):
        h = jload(HISTORY_F, [])
        h.append(dict(id=len(h) + 1, time=datetime.datetime.now().isoformat(timespec="seconds"),
                      user=self.sh.user["name"] if self.sh and self.sh.user else "root",
                      action=action, undone=False, **kw))
        jsave(HISTORY_F, h)

    # ---- dispatch --------------------------------------------------------
    def run(self, args):
        if not args or args[0] in ("help", "-h", "--help"):
            print(WINST_HELP)
            return 0
        if args[0] in ("-v", "--version", "version"):
            print(f"winst {VERSION} ({CODENAME})")
            return 0
        self.refresh()
        alias = {"add": "install", "rm": "remove", "delete": "remove", "show": "info", "ls": "list",
                 "find": "search", "full-upgrade": "upgrade", "dist-upgrade": "upgrade"}
        cmd = alias.get(args[0], args[0])
        rest = args[1:]
        flags = {a for a in rest if a.startswith("-")}
        names = [a for a in rest if not a.startswith("-")]
        if cmd == "purge":
            cmd, flags = "remove", flags | {"--purge"}
        fn = getattr(self, "c_" + cmd, None)
        if fn is None:
            raise WinstError(f"invalid operation '{args[0]}'. See 'winst help'")
        needs_root = cmd in ROOT_CMDS or (cmd == "source" and names[:1] in (["add"], ["remove"]))
        if needs_root and not (self.sh and self.sh.elevated):
            raise WinstError(
                "could not open lock file /var/lib/winst/lock - permission denied\n"
                f"   Are you root? Try:  sudo winst {' '.join(args)}")
        return fn(names, flags) or 0

    # ---- read-only commands ---------------------------------------------
    def c_search(self, names, flags):
        if not names:
            raise WinstError("search what? Usage: winst search <term>")
        terms = [t.lower() for t in names]
        hits = []
        for n, m in sorted(self.pkgs.items()):
            hay = f"{n} {m['desc']} {m['category']} {m['kind']}".lower()
            if all(t in hay for t in terms):
                hits.append(n)
        if not hits:
            print(f"No packages found for '{' '.join(names)}'.")
            sug = difflib.get_close_matches(names[0], list(self.pkgs), n=3, cutoff=0.5)
            if sug:
                print("Similar: " + ", ".join(sug))
            return 1
        for n in hits:
            m, tag = self.pkgs[n], ""
            if n in self.installed:
                tag = green(" [installed]") if n not in self.upgradable() else yellow(" [upgradable]")
            print(f"{bold(n)}/{m['version']}{tag}\n    {m['desc']}  ({m['category']})")

    def c_list(self, names, flags):
        up = set(self.upgradable())
        rows = []
        for n, m in sorted(self.pkgs.items()):
            st = "" if n not in self.installed else ("upgradable" if n in up else "installed")
            if "--installed" in flags and not st:
                continue
            if "--upgradable" in flags and st != "upgradable":
                continue
            rows.append((n, m["version"], st, m["desc"]))
        for n, v, st, d in rows:
            col = green if st == "installed" else yellow if st else dim
            print(f"{n:<22}{v:<9}{col(f'{st:<12}')}{d}")
        print(dim(f"{len(rows)} packages  (index revision {self.rev})"))

    def c_info(self, names, flags):
        for n in names:
            m = self.pkgs.get(n)
            if not m:
                raise WinstError(self.unknown(n))
            rec = self.installed.get(n)
            rdeps = [d for d, r in self.installed.items() if n in r["deps"]]
            status = "not installed"
            if rec:
                status = f"installed {rec['version']} ({rec['reason']})"
            print(f"{bold('Package')}: {n}\n{bold('Version')}: {m['version']}\n"
                  f"{bold('Type')}: {m['kind']}   {bold('Category')}: {m['category']}\n"
                  f"{bold('Depends')}: {', '.join(m['deps']) or '-'}\n"
                  f"{bold('Conflicts')}: {', '.join(m['conflicts']) or '-'}\n"
                  f"{bold('Required by')}: {', '.join(rdeps) or '-'}\n"
                  f"{bold('Size')}: {fmt_kb(m['size_kb'])}\n{bold('Status')}: {status}\n"
                  f"{bold('SHA256')}: {sha_of(n, m)[:32]}...\n{bold('Description')}: {m['desc']}\n")

    def c_history(self, names, flags):
        h = jload(HISTORY_F, [])
        if not h:
            print("No transactions yet.")
        for e in h[-20:]:
            detail = []
            for k in ("installed", "upgraded", "removed"):
                if e.get(k):
                    detail.append(f"{k}: " + ", ".join(x if isinstance(x, str) else x["name"] for x in e[k]))
            flag = dim(" (undone)") if e["undone"] else ""
            print(f"#{e['id']:<3}{e['time']}  {e['user']:<8}{e['action']:<12}{'; '.join(detail)}{flag}")

    def c_check(self, names, flags):
        bad = 0
        for n, r in sorted(self.installed.items()):
            missing = [f for f in r["files"] if not hpath(f).exists()]
            if missing:
                bad += 1
                print(red(f"{n}: {len(missing)} missing file(s), e.g. {missing[0]}"))
        print(green("All installed packages verified.") if not bad else
              yellow(f"{bad} package(s) damaged. Fix: sudo winst install <pkg> after removing it."))
        return 1 if bad else 0

    def c_owns(self, names, flags):
        if not names:
            raise WinstError("owns what? Usage: winst owns <file>")
        v = self.sh.vresolve(names[0]) if self.sh else names[0]
        for n, r in self.installed.items():
            if v in r["files"] or v in r["conf"]:
                print(f"{v} is owned by {bold(n)} {r['version']}")
                return 0
        print(f"no package owns {v}")
        return 1

    # ---- sources ---------------------------------------------------------
    def c_source(self, names, flags):
        srcs = jload(SOURCES_F, [])
        sub = names[0] if names else "list"
        if sub == "list":
            print("Official: mirror.windos.local/stable (built-in)")
            for s in srcs:
                print("Extra:    " + s)
        elif sub in ("add", "remove") and len(names) == 2:
            url = names[1]
            if sub == "add":
                if not re.match(r"^(https?|file)://", url):
                    raise WinstError("source must start with http://, https:// or file://")
                if url not in srcs:
                    srcs.append(url)
            elif url in srcs:
                srcs.remove(url)
            else:
                raise WinstError("no such source")
            jsave(SOURCES_F, srcs)
            print(f"{sub}: {url}  (run 'sudo winst update' to sync)")
        else:
            raise WinstError("usage: winst source list | add <url> | remove <url>")

    # ---- write commands --------------------------------------------------
    def c_update(self, names, flags):
        rev = self.rev
        print("Hit:1 mirror.windos.local/stable InRelease")
        if rev + 1 in REVISIONS:
            rev += 1
            print(f"Get:2 mirror.windos.local/stable revision {rev}  [{len(REVISIONS[rev])} package changes]")
        custom = {}
        for url in jload(SOURCES_F, []):
            try:
                with urllib.request.urlopen(url, timeout=6) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                data = data.get("packages", data)
                custom[url] = {n: norm_pkg(d) for n, d in data.items()}
                print(f"Get:+ {url}  [{len(custom[url])} packages]")
            except Exception as e:  # noqa
                custom[url] = self.custom.get(url, {})
                print(red(f"Err: {url} ({e}) - using cached copy"))
        jsave(INDEX_F, {"revision": rev, "custom": custom})
        self.refresh()
        up = self.upgradable()
        print(f"Package lists updated (revision {rev}).")
        print(f"{len(up)} package(s) can be upgraded." + (" Run: sudo winst upgrade" if up else
                                                          " Everything is up to date."))

    def c_install(self, names, flags):
        if not names:
            raise WinstError("no packages specified. Usage: sudo winst install <package...>")
        todo = []
        for n in dict.fromkeys(names):
            if n not in self.pkgs:
                raise WinstError(self.unknown(n))
            rec = self.installed.get(n)
            if rec and vkey(rec["version"]) >= vkey(self.pkgs[n]["version"]):
                print(f"{n} is already the newest version ({rec['version']})")
                if rec["reason"] != "manual":
                    rec["reason"] = "manual"
                    self.save_installed()
                    print(dim(f"  (marked {n} as manually installed)"))
                continue
            todo.append(n)
        if not todo:
            return 0
        plan = resolve(todo, self.pkgs, self.installed)
        return self.transact("install", plan, set(todo), flags)

    def c_upgrade(self, names, flags):
        up = self.upgradable()
        if not up:
            print("0 upgraded, 0 newly installed. System is up to date.")
            return 0
        return self.transact("upgrade", resolve(up, self.pkgs, self.installed), set(), flags)

    def transact(self, action, plan, manual, flags):
        new = [n for n in plan if n not in self.installed]
        upg = [n for n in plan if n in self.installed]
        print("Reading package lists... Done\nResolving dependencies... Done")
        if new:
            print("The following NEW packages will be installed:\n  " + " ".join(new))
        if upg:
            print("The following packages will be UPGRADED:\n  " + " ".join(
                f"{n} ({self.installed[n]['version']} -> {self.pkgs[n]['version']})" for n in upg))
        dl = sum(self.pkgs[n]["size_kb"] for n in plan)
        print(f"{len(new)} new, {len(upg)} upgraded. Download {fmt_kb(dl)}, disk use {fmt_kb(dl * 2)}.")
        if flags & {"-s", "--dry-run"}:
            print("(dry run) nothing was changed.")
            return 0
        if not (flags & {"-y", "--yes"}) and not confirm("Do you want to continue? [Y/n] "):
            print("Abort.")
            return 1
        done = []
        try:
            with lock():
                for n in plan:
                    meta, prev = self.pkgs[n], self.installed.get(n)
                    progress(f"{n} {meta['version']}", meta["size_kb"])
                    payload = payload_of(n, meta["version"])
                    if hashlib.sha256(payload).hexdigest() != sha_of(n, meta):
                        raise WinstError(f"checksum mismatch for {n} - package rejected")
                    CACHE_D.mkdir(parents=True, exist_ok=True)
                    (CACHE_D / f"{n}_{meta['version']}.wpkg").write_bytes(payload)
                    if prev:
                        erase_pkg(n, prev)
                    reason = "manual" if n in manual else (prev["reason"] if prev else "auto")
                    self.install_record(n, reason)
                    done.append((n, prev))
                    self.save_installed()
        except BaseException as e:  # roll the whole transaction back
            print(red("\nTransaction failed - rolling back..."))
            for n, prev in reversed(done):
                erase_pkg(n, self.installed[n], purge=prev is None)
                if prev:
                    write_pkg(n, prev)
                    self.installed[n] = prev
                else:
                    del self.installed[n]
            self.save_installed()
            if isinstance(e, KeyboardInterrupt):
                raise WinstError("interrupted by user")
            raise WinstError(str(e))
        self.log_history(action, installed=[n for n, p in done if p is None],
                         upgraded=[{"name": n, "from": p["version"]} for n, p in done if p])
        print(green(f"Done. {len(new)} installed, {len(upg)} upgraded."))
        for n in new:
            if self.pkgs[n]["kind"] == "game":
                print(f"  {cyan('>')} play with:  run {n}")

    def dependents_closure(self, rm):
        rm = set(rm)
        grew = True
        while grew:
            grew = False
            for d, r in self.installed.items():
                if d not in rm and rm & set(r["deps"]):
                    rm.add(d)
                    grew = True
        return rm

    def c_remove(self, names, flags):
        if not names:
            raise WinstError("no packages specified. Usage: sudo winst remove <package...>")
        for n in names:
            if n not in self.installed:
                raise WinstError(f"package '{n}' is not installed")
            if n in PROTECTED_PKGS:
                raise WinstError(f"refusing to remove essential package '{n}'")
        rm = set(names)
        if "--cascade" in flags:
            rm = self.dependents_closure(rm)
        for n in names:
            blockers = [d for d, r in self.installed.items() if n in r["deps"] and d not in rm]
            if blockers:
                raise WinstError(f"{n} is required by: {', '.join(blockers)}\n"
                                 f"   Remove those too, or use --cascade")
        self.do_remove(sorted(rm), flags, "remove")

    def orphans(self):
        keep, stack = set(), [n for n, r in self.installed.items() if r["reason"] == "manual"]
        while stack:
            n = stack.pop()
            if n not in keep and n in self.installed:
                keep.add(n)
                stack.extend(self.installed[n]["deps"])
        return sorted(n for n in self.installed if n not in keep and n not in PROTECTED_PKGS)

    def c_autoremove(self, names, flags):
        orph = self.orphans()
        if not orph:
            print("0 packages to remove.")
            return 0
        self.do_remove(orph, flags, "autoremove")

    def do_remove(self, rm, flags, action):
        print("The following packages will be REMOVED:\n  " + " ".join(rm))
        if flags & {"-s", "--dry-run"}:
            print("(dry run) nothing was changed.")
            return
        if not (flags & {"-y", "--yes"}) and not confirm("Do you want to continue? [Y/n] "):
            print("Abort.")
            return
        purge, removed = "--purge" in flags, []
        with lock():
            for n in rm:
                rec = self.installed.pop(n)
                erase_pkg(n, rec, purge)
                removed.append({"name": n, "reason": rec["reason"]})
                print(f"  removing {n} {rec['version']}" + (" (purged)" if purge else ""))
            self.save_installed()
        self.log_history(action, removed=removed)
        orph = self.orphans()
        print(green("Done."))
        if orph and action != "autoremove":
            print(dim(f"{len(orph)} package(s) no longer needed: {' '.join(orph)}  -> sudo winst autoremove"))

    def c_clean(self, names, flags):
        files = list(CACHE_D.glob("*.wpkg")) if CACHE_D.exists() else []
        for f in files:
            f.unlink()
        print(f"Removed {len(files)} cached package file(s).")

    def c_undo(self, names, flags):
        h = jload(HISTORY_F, [])
        entry = next((e for e in reversed(h) if e["action"] in ("install", "remove") and not e["undone"]), None)
        if not entry:
            print("Nothing to undo.")
            return 1
        print(f"Reverting transaction #{entry['id']} ({entry['action']}, {entry['time']})")
        if entry["action"] == "install":
            targets = list(entry["installed"])
            if not targets:
                print("That transaction only upgraded packages; cannot undo.")
                return 1
            self.c_remove(targets, flags | {"-y"} if "-y" in flags else flags)
        else:
            targets = [r["name"] for r in entry["removed"]]
            self.c_install(targets, flags)
        h = jload(HISTORY_F, [])
        for e in h:
            if e["id"] == entry["id"]:
                e["undone"] = True
        jsave(HISTORY_F, h)


# --------------------------------------------------------------------------
# System services & Game Mode
# --------------------------------------------------------------------------
DEFAULT_SERVICES = {
    "windd":        dict(running=True, essential=True,  hog=False, ram=4,  desc="init / service supervisor"),
    "netd":         dict(running=True, essential=True,  hog=False, ram=6,  desc="networking"),
    "audiod":       dict(running=True, essential=True,  hog=False, ram=12, desc="audio server"),
    "compositor":   dict(running=True, essential=True,  hog=False, ram=38, desc="wind-compositor-lite"),
    "indexer":      dict(running=True, essential=False, hog=True,  ram=55, desc="file search indexer"),
    "updater":      dict(running=True, essential=False, hog=True,  ram=28, desc="background update checker"),
    "bluetoothd":   dict(running=True, essential=False, hog=True,  ram=14, desc="bluetooth stack"),
    "printd":       dict(running=True, essential=False, hog=True,  ram=22, desc="print spooler"),
    "cron-lite":    dict(running=True, essential=False, hog=True,  ram=6,  desc="scheduled tasks"),
}
DEFAULT_CFG = dict(hostname="windos", gamemode=False, gm_stopped=[], game_auto=True,
                   favorites=[], recent=[], playtime={}, governor="schedutil")
BASE_RAM = 96  # MB used by the lean kernel + shell

ALIASES = {"dir": "ls", "type": "cat", "more": "cat", "cls": "clear", "md": "mkdir", "rd": "rmdir",
           "del": "rm", "erase": "rm", "copy": "cp", "move": "mv", "ren": "mv", "rename": "mv",
           "tasklist": "ps", "ver": "uname", "chdir": "cd", "where": "which", "findstr": "grep",
           "neofetch": "windfetch", "hub": "wind", "poweroff": "exit", "shutdown": "exit",
           "quit": "exit", "logout": "exit"}

SHELL_HELP = f"""{bold('WindOS shell')}  - Linux + Windows CMD commands, one prompt
  {cyan('Navigate')}   wind (Hub)   go <name>   cd  pwd  ls/dir
  {cyan('Files')}      cat/type  cp/copy  mv/move/ren  rm/del  mkdir/md  rmdir/rd  touch  grep/findstr  echo (> >>)
  {cyan('Packages')}   winst <cmd>  - system changes need sudo, e.g.  sudo winst install raceline
  {cyan('Gaming')}     gamemode on|off|auto|status   run <game|file.exe>   fav add|remove|list <name>
  {cyan('System')}     sudo <cmd>  winctl list|start|stop|restart <svc>  windfetch  ps  free  uptime  uname/ver
  {cyan('Users')}      whoami  groups  useradd [--sudo] <name>  passwd [user]
  {cyan('Host')}       host <command>   run a real command on the host OS (cmd.exe / sh)
  {cyan('Other')}      history  env  which  date  clear/cls  reboot  exit"""


# --------------------------------------------------------------------------
# The shell
# --------------------------------------------------------------------------
class Shell:
    def __init__(self):
        self.user = None
        self.cwd = "/"
        self.elevated = False
        self.sudo_ts = 0.0
        self.hist = []
        self.running = True
        self.t0 = time.time()
        self.winst = Winst(self)
        self.cfg = dict(DEFAULT_CFG)
        self.svc = {}

    # ---- persistence -----------------------------------------------------
    def save_cfg(self):
        jsave(CONFIG_F, self.cfg)

    def save_svc(self):
        jsave(SERVICES_F, self.svc)

    def load_state(self):
        self.cfg = {**DEFAULT_CFG, **jload(CONFIG_F, {})}
        self.svc = jload(SERVICES_F, json.loads(json.dumps(DEFAULT_SERVICES)))

    # ---- first boot / login / boot ---------------------------------------
    def first_boot(self):
        print(bold("\n  Welcome to WindOS - first boot setup\n"))
        for d in DIRS:
            hpath("/" + d).mkdir(parents=True, exist_ok=True)
        host = os.environ.get("WINDOS_HOST") or prompt("  Hostname [windos]: ", "windos")
        name = os.environ.get("WINDOS_USER") or prompt("  Username: ", "player")
        name = re.sub(r"[^a-z0-9_-]", "", name.lower()) or "player"
        while True:
            pw = ask_password("  Password: ")
            if pw and pw == ask_password("  Repeat password: "):
                break
            print(red("  Passwords empty or not matching, try again."))
        salt, h = hash_pw(pw)
        users = {name: dict(salt=salt, hash=h, groups=["sudo", "games", "users"], home=f"/home/{name}")}
        jsave(USERS_F, users)
        hpath(f"/home/{name}").mkdir(parents=True, exist_ok=True)
        hpath(f"/home/{name}/Games").mkdir(exist_ok=True)
        hpath(f"/home/{name}/Documents").mkdir(exist_ok=True)
        hpath(f"/home/{name}/welcome.txt").write_text(
            "Welcome to WindOS!\n\nTry:  wind          (open the Hub)\n"
            "      sudo winst install raceline\n      gamemode on\n      dir  /  cls  /  type welcome.txt\n",
            encoding="utf-8")
        self.cfg = {**DEFAULT_CFG, "hostname": host}
        self.svc = json.loads(json.dumps(DEFAULT_SERVICES))
        self.save_cfg()
        self.save_svc()
        jsave(HISTORY_F, [])
        jsave(SOURCES_F, [])
        print("  Installing base system...")
        self.winst.bootstrap()
        log_auth(f"first boot: created user {name}")
        print(green(f"  Done. User '{name}' created (sudo enabled).\n"))

    def login(self):
        users = jload(USERS_F, {})
        for _ in range(3):
            name = os.environ.get("WINDOS_USER") or prompt(f"{self.cfg['hostname']} login: ")
            pw = ask_password("Password: ")
            u = users.get(name)
            if u and secrets.compare_digest(hash_pw(pw, u["salt"])[1], u["hash"]):
                self.user = {"name": name, **u}
                self.cwd = u["home"]
                log_auth(f"login ok: {name}")
                return True
            log_auth(f"login FAILED: {name}")
            print(red("Login incorrect"))
            sleep(0.8)
        return False

    def boot(self):
        host_os = {"Darwin": "macOS", "Windows": "Windows", "Linux": "Linux"}.get(
            platform.system(), platform.system())
        gm = self.cfg["gamemode"]
        steps = [f"Initializing WindOS emulation layer on {host_os} ({platform.machine()})",
                 f"Mounting virtual root {ROOT}", "Loading winst package database"]
        for n, s in self.svc.items():
            s["running"] = not (s["hog"] and gm)
            steps.append(f"Starting {n:<11} - {s['desc']}" if s["running"] else
                         f"Skipping {n:<11} - {s['desc']} (game mode)")
        t = time.time()
        for s in steps:
            tag = green("  OK  ") if not s.startswith("Skipping") else yellow(" SKIP ")
            print(f"[{tag}] {s}")
            sleep(0.04)
        self.save_svc()
        print(dim(f"Boot finished in {0.6 + random.random() * 0.4:.2f}s  "
                  f"(idle RAM {self.ram_used()} MB)\n"))

    def ram_used(self):
        return BASE_RAM + sum(s["ram"] for s in self.svc.values() if s["running"])

    # ---- paths & permissions --------------------------------------------
    def vresolve(self, p):
        p = p.replace("\\", "/")
        if re.match(r"^[A-Za-z]:", p):
            p = p[2:]
        if p == "~" or p.startswith("~/"):
            p = self.user["home"] + p[1:]
        if not p.startswith("/"):
            p = self.cwd.rstrip("/") + "/" + p
        parts = []
        for seg in p.split("/"):
            if seg in ("", "."):
                continue
            if seg == "..":
                if parts:
                    parts.pop()
            else:
                parts.append(seg)
        return "/" + "/".join(parts)

    def can_write(self, v):
        if self.elevated:
            return True
        home = self.user["home"]
        return v == home or v.startswith(home + "/") or v == "/tmp" or v.startswith("/tmp/")

    def deny(self, cmd, p):
        print(red(f"{cmd}: cannot modify '{p}': Permission denied") + dim(f"  (try: sudo {cmd} ...)"))
        return 1

    @staticmethod
    def is_flag(a):
        return (a.startswith("-") and len(a) > 1) or (a.startswith("/") and len(a) == 2 and a[1].isalpha())

    def fmt_name(self, e):
        return cyan(e.name + "/") if e.is_dir() else e.name

    def short_cwd(self):
        home = self.user["home"]
        return "~" + self.cwd[len(home):] if self.cwd == home or self.cwd.startswith(home + "/") else self.cwd

    # ---- command execution ----------------------------------------------
    def execute(self, line):
        line = line.strip()
        if not line or line.startswith("#"):
            return 0
        self.hist.append(line)
        try:
            tokens = shlex.split(line.replace("\\", "/"))
        except ValueError as e:
            print(red(f"syntax error: {e}"))
            return 2
        sub = {"$USER": self.user["name"], "$HOME": self.user["home"], "$PWD": self.cwd}
        tokens = [sub.get(t, t) for t in tokens]
        redir = None
        for op in (">>", ">"):
            if op in tokens:
                i = tokens.index(op)
                if i + 1 >= len(tokens):
                    print(red("syntax error: missing redirect target"))
                    return 2
                redir, tokens, target = op, tokens[:i], tokens[i + 1]
                break
        if redir:
            v = self.vresolve(target)
            if not self.can_write(v):
                return self.deny("write", target)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = self.dispatch(tokens)
            p = hpath(v)
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a" if redir == ">>" else "w", encoding="utf-8") as f:
                f.write(re.sub(r"\033\[[0-9;]*m", "", buf.getvalue()))
            return rc
        return self.dispatch(tokens)

    def dispatch(self, tokens):
        if not tokens:
            return 0
        name = tokens[0].lower()
        name = ALIASES.get(name, name)
        fn = getattr(self, "cmd_" + name, None) if re.match(r"^[a-z0-9_]+$", name) else None
        if fn is None:
            print(red(f"{tokens[0]}: command not found") + dim("  (type 'help', or 'go " + tokens[0] + "')"))
            return 127
        try:
            return fn(tokens[1:]) or 0
        except KeyboardInterrupt:
            print()
            return 130
        except WinstError as e:
            print(red("E: ") + str(e))
            return 100
        except OSError as e:
            print(red(f"{name}: {e.strerror or e}"))
            return 1

    # ---- sudo ------------------------------------------------------------
    def cmd_sudo(self, args):
        if not args:
            print("usage: sudo <command>")
            return 1
        if "sudo" not in self.user["groups"]:
            print(red(f"{self.user['name']} is not in the sudoers file. This incident will be reported."))
            log_auth(f"sudo DENIED (not sudoer): {self.user['name']}: {' '.join(args)}")
            return 1
        if time.time() - self.sudo_ts > SUDO_TTL:
            users = jload(USERS_F, {})
            u = users[self.user["name"]]
            for attempt in range(3):
                pw = ask_password(f"[sudo] password for {self.user['name']}: ")
                if secrets.compare_digest(hash_pw(pw, u["salt"])[1], u["hash"]):
                    break
                print("Sorry, try again.")
                log_auth(f"sudo bad password: {self.user['name']}")
            else:
                print(red("sudo: 3 incorrect password attempts"))
                return 1
        self.sudo_ts = time.time()
        log_auth(f"sudo: {self.user['name']} : {' '.join(args)}")
        self.elevated = True
        try:
            return self.dispatch(args)
        finally:
            self.elevated = False

    def cmd_winst(self, args):
        return self.winst.run(args)

    # ---- file commands ---------------------------------------------------
    def cmd_pwd(self, args):
        print(self.cwd)

    def cmd_cd(self, args):
        v = self.vresolve(args[0]) if args else self.user["home"]
        if not hpath(v).is_dir():
            print(red(f"cd: {args[0] if args else v}: No such directory"))
            return 1
        self.cwd = v

    def cmd_ls(self, args):
        flags = [a for a in args if self.is_flag(a)]
        paths = [a for a in args if not self.is_flag(a)] or ["."]
        long_ = any(f.startswith("-") and "l" in f for f in flags)
        rc = 0
        for p in paths:
            v = self.vresolve(p)
            h = hpath(v)
            if not h.exists():
                print(red(f"ls: cannot access '{p}': No such file or directory"))
                rc = 1
                continue
            entries = [h] if h.is_file() else sorted(h.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            if len(paths) > 1:
                print(f"{v}:")
            if long_:
                for e in entries:
                    st = e.stat()
                    print(f"{'d' if e.is_dir() else '-'}rwxr-xr-x {st.st_size:>8} "
                          f"{datetime.datetime.fromtimestamp(st.st_mtime):%b %d %H:%M} {self.fmt_name(e)}")
            elif entries:
                print("  ".join(self.fmt_name(e) for e in entries))
        return rc

    def cmd_cat(self, args):
        files = [a for a in args if not self.is_flag(a)]
        if not files:
            print("usage: cat <file>")
            return 1
        for f in files:
            v = self.vresolve(f)
            if v == PROTECTED_USERS_FILE and not self.elevated:
                print(red(f"cat: {f}: Permission denied"))
                return 1
            h = hpath(v)
            if not h.is_file():
                print(red(f"cat: {f}: No such file"))
                return 1
            print(h.read_text(encoding="utf-8", errors="replace"), end="")
            if not h.read_text(encoding="utf-8", errors="replace").endswith("\n"):
                print()

    def cmd_echo(self, args):
        print(" ".join(args))

    def cmd_touch(self, args):
        for a in [x for x in args if not self.is_flag(x)]:
            v = self.vresolve(a)
            if not self.can_write(v):
                return self.deny("touch", a)
            hpath(v).parent.mkdir(parents=True, exist_ok=True)
            hpath(v).touch()

    def cmd_mkdir(self, args):
        for a in [x for x in args if not self.is_flag(x)]:
            v = self.vresolve(a)
            if not self.can_write(v):
                return self.deny("mkdir", a)
            hpath(v).mkdir(parents=True, exist_ok=True)

    def cmd_rmdir(self, args):
        for a in [x for x in args if not self.is_flag(x)]:
            v = self.vresolve(a)
            if not self.can_write(v):
                return self.deny("rmdir", a)
            try:
                hpath(v).rmdir()
            except OSError:
                print(red(f"rmdir: failed to remove '{a}': not empty or missing"))
                return 1

    def cmd_rm(self, args):
        rec = any(a in ("-r", "-rf", "-fr", "-R", "/s") for a in args)
        for a in [x for x in args if not self.is_flag(x)]:
            v = self.vresolve(a)
            if v == "/":
                print(red("rm: refusing to remove '/'"))
                return 1
            if not self.can_write(v):
                return self.deny("rm", a)
            h = hpath(v)
            if not h.exists():
                print(red(f"rm: cannot remove '{a}': No such file or directory"))
                return 1
            if h.is_dir():
                if not rec:
                    print(red(f"rm: cannot remove '{a}': Is a directory (use -r)"))
                    return 1
                shutil.rmtree(h)
            else:
                h.unlink()

    def _two(self, args, name):
        a = [x for x in args if not self.is_flag(x)]
        if len(a) < 2:
            print(f"usage: {name} <source> <destination>")
            return None
        src, dst = self.vresolve(a[0]), self.vresolve(a[-1])
        if not hpath(src).exists():
            print(red(f"{name}: cannot stat '{a[0]}': No such file or directory"))
            return None
        if hpath(dst).is_dir():
            dst = dst.rstrip("/") + "/" + src.rsplit("/", 1)[-1]
        if not self.can_write(dst) or (name == "mv" and not self.can_write(src)):
            self.deny(name, a[-1])
            return None
        return src, dst

    def cmd_cp(self, args):
        r = self._two(args, "cp")
        if r:
            s, d = hpath(r[0]), hpath(r[1])
            shutil.copytree(s, d) if s.is_dir() else shutil.copy2(s, d)
            return 0
        return 1

    def cmd_mv(self, args):
        r = self._two(args, "mv")
        if r:
            shutil.move(str(hpath(r[0])), str(hpath(r[1])))
            return 0
        return 1

    def cmd_grep(self, args):
        a = [x for x in args if not self.is_flag(x)]
        if len(a) < 2:
            print("usage: grep <pattern> <file>")
            return 1
        h = hpath(self.vresolve(a[1]))
        if not h.is_file():
            print(red(f"grep: {a[1]}: No such file"))
            return 1
        icase = any("i" in f for f in args if f.startswith("-")) or "/i" in args
        found = False
        for i, line in enumerate(h.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if (a[0].lower() in line.lower()) if icase else (a[0] in line):
                print(f"{dim(str(i) + ':')}{line}")
                found = True
        return 0 if found else 1

    def cmd_clear(self, args):
        if USE_COLOR:
            print("\033[2J\033[H", end="")

    # ---- info commands ---------------------------------------------------
    def cmd_help(self, args):
        print(SHELL_HELP)

    def cmd_whoami(self, args):
        print("root" if self.elevated else self.user["name"])

    def cmd_hostname(self, args):
        print(self.cfg["hostname"])

    def cmd_groups(self, args):
        print(" ".join(self.user["groups"]))

    def cmd_uname(self, args):
        host = f"{platform.system()} {platform.release()}"
        print(f"WindOS {VERSION} ({CODENAME}) {self.cfg['hostname']} emulated-on-{host} {platform.machine()}")

    def cmd_date(self, args):
        print(datetime.datetime.now().strftime("%a %b %d %H:%M:%S %Y"))

    def cmd_uptime(self, args):
        s = int(time.time() - self.t0)
        print(f"up {s // 3600}h {s % 3600 // 60}m {s % 60}s   game mode: {'ON' if self.cfg['gamemode'] else 'off'}")

    def cmd_free(self, args):
        total, used = 8192, self.ram_used()
        print(f"{'':<8}{'total':>8}{'used':>8}{'free':>8}   (MB, emulated)")
        print(f"{'Mem:':<8}{total:>8}{used:>8}{total - used:>8}")

    def cmd_env(self, args):
        for k, v in (("USER", self.user["name"]), ("HOME", self.user["home"]), ("PWD", self.cwd),
                     ("HOSTNAME", self.cfg["hostname"]), ("SHELL", "/usr/bin/windsh"),
                     ("WINDOS_VERSION", VERSION), ("GAMEMODE", int(self.cfg["gamemode"]))):
            print(f"{k}={v}")

    def cmd_which(self, args):
        for a in args:
            if hasattr(self, "cmd_" + ALIASES.get(a.lower(), a.lower())):
                print(f"{a}: shell builtin")
            elif hpath(f"/usr/bin/{a}").exists():
                print(f"/usr/bin/{a}")
            else:
                print(f"{a} not found")

    def cmd_history(self, args):
        for i, h in enumerate(self.hist, 1):
            print(f"{i:>4}  {h}")

    def cmd_ps(self, args):
        print(f"{'PID':>6}  {'NAME':<12}{'RAM':>7}  DESCRIPTION")
        for n, s in self.svc.items():
            if s["running"]:
                pid = 100 + int(hashlib.md5(n.encode()).hexdigest(), 16) % 900
                print(f"{pid:>6}  {n:<12}{s['ram']:>5}MB  {s['desc']}")
        print(dim(f"total {self.ram_used()} MB (incl. {BASE_RAM} MB kernel+shell)"))

    def cmd_windfetch(self, args):
        inst = len(self.winst_installed())
        runsvc = sum(1 for s in self.svc.values() if s["running"])
        host = f"{platform.system()} {platform.release()}"
        logo = [cyan("  \\  \\  /  /  "), cyan("   \\  \\/  /   "), cyan("    \\ /\\ /    "),
                cyan("     V  V     "), cyan("   W I N D    "), cyan("      O S     ")]
        info = [f"{bold(self.user['name'])}@{bold(self.cfg['hostname'])}", "-" * 24,
                f"OS:       WindOS {VERSION} ({CODENAME})", f"Host:     {host} (emulated)",
                f"Packages: {inst} (winst)", f"Services: {runsvc}/{len(self.svc)} running",
                f"RAM:      {self.ram_used()} MB idle",
                f"Game mode: {green('ON') if self.cfg['gamemode'] else yellow('off')}   "
                f"Governor: {self.cfg['governor']}"]
        for i in range(max(len(logo), len(info))):
            print((logo[i] if i < len(logo) else " " * 14) + "  " + (info[i] if i < len(info) else ""))

    def winst_installed(self):
        return jload(INSTALLED_F, {})

    # ---- users -----------------------------------------------------------
    def cmd_useradd(self, args):
        if not self.elevated:
            print(red("useradd: Permission denied") + dim("  (try: sudo useradd <name>)"))
            return 1
        names = [a for a in args if not a.startswith("-")]
        if not names:
            print("usage: sudo useradd [--sudo] <name>")
            return 1
        name = re.sub(r"[^a-z0-9_-]", "", names[0].lower())
        users = jload(USERS_F, {})
        if not name or name in users:
            print(red("useradd: invalid or existing user"))
            return 1
        pw = ask_password(f"New password for {name}: ")
        if not pw:
            print(red("useradd: empty password"))
            return 1
        salt, h = hash_pw(pw)
        groups = ["users", "games"] + (["sudo"] if "--sudo" in args else [])
        users[name] = dict(salt=salt, hash=h, groups=groups, home=f"/home/{name}")
        jsave(USERS_F, users)
        hpath(f"/home/{name}").mkdir(parents=True, exist_ok=True)
        log_auth(f"useradd {name} groups={groups}")
        print(green(f"User '{name}' created ({', '.join(groups)})."))

    def cmd_passwd(self, args):
        target = args[0] if args else self.user["name"]
        users = jload(USERS_F, {})
        if target not in users:
            print(red(f"passwd: user '{target}' does not exist"))
            return 1
        if target != self.user["name"] and not self.elevated:
            print(red("passwd: Permission denied") + dim(f"  (try: sudo passwd {target})"))
            return 1
        if not self.elevated:
            old = ask_password("Current password: ")
            if not secrets.compare_digest(hash_pw(old, users[target]["salt"])[1], users[target]["hash"]):
                print(red("passwd: authentication failure"))
                return 1
        p1 = ask_password("New password: ")
        if not p1 or p1 != ask_password("Repeat new password: "):
            print(red("passwd: passwords empty or not matching"))
            return 1
        users[target]["salt"], users[target]["hash"] = hash_pw(p1)
        jsave(USERS_F, users)
        log_auth(f"passwd changed for {target}")
        print(green("Password updated."))

    # ---- host passthrough ------------------------------------------------
    def cmd_host(self, args):
        if not args:
            print("usage: host <command>   (runs on the real host OS, outside the sandbox)")
            return 1
        r = subprocess.run(" ".join(args), shell=True, cwd=str(hpath(self.cwd)))
        return r.returncode

    # ---- services --------------------------------------------------------
    def cmd_winctl(self, args):
        sub = args[0] if args else "list"
        if sub in ("list", "status"):
            for n, s in self.svc.items():
                st = green("running") if s["running"] else red("stopped")
                tag = dim("essential") if s["essential"] else dim("optional ")
                print(f"{n:<12}{st:<18}{tag}  {s['ram']:>3}MB  {s['desc']}")
            print(dim(f"idle RAM: {self.ram_used()} MB"))
            return 0
        if sub not in ("start", "stop", "restart") or len(args) < 2:
            print("usage: winctl list | [sudo] start|stop|restart <service>")
            return 1
        if not self.elevated:
            print(red("winctl: Permission denied") + dim(f"  (try: sudo winctl {' '.join(args)})"))
            return 1
        n = args[1]
        if n not in self.svc:
            print(red(f"winctl: unknown service '{n}'"))
            return 1
        if sub == "stop" and self.svc[n]["essential"]:
            print(red(f"winctl: refusing to stop essential service '{n}'"))
            return 1
        self.svc[n]["running"] = sub != "stop"
        self.save_svc()
        print(green(f"{n}: {'stopped' if sub == 'stop' else 'running'}"))

    # ---- game mode -------------------------------------------------------
    def gm_on(self):
        stopped = [n for n, s in self.svc.items() if s["running"] and s["hog"]]
        for n in stopped:
            self.svc[n]["running"] = False
        self.cfg.update(gamemode=True, gm_stopped=stopped, governor="performance")
        self.save_cfg()
        self.save_svc()
        return stopped

    def gm_off(self):
        for n in self.cfg["gm_stopped"]:
            if n in self.svc:
                self.svc[n]["running"] = True
        restored = self.cfg["gm_stopped"]
        self.cfg.update(gamemode=False, gm_stopped=[], governor="schedutil")
        self.save_cfg()
        self.save_svc()
        return restored

    def cmd_gamemode(self, args):
        sub = args[0] if args else "status"
        if sub == "on":
            if self.cfg["gamemode"]:
                print("Game mode is already on.")
                return 0
            before = self.ram_used()
            stopped = self.gm_on()
            print(green("Game mode ON") + f" - paused {len(stopped)} background services "
                  f"({', '.join(stopped) or 'none'})\n  CPU governor: performance   "
                  f"compositor: fullscreen bypass   RAM {before} -> {self.ram_used()} MB")
        elif sub == "off":
            r = self.gm_off()
            print(yellow("Game mode off") + f" - restored {len(r)} services. RAM now {self.ram_used()} MB")
        elif sub == "auto":
            self.cfg["game_auto"] = not self.cfg["game_auto"]
            self.save_cfg()
            print(f"Auto game mode when launching games: {'ON' if self.cfg['game_auto'] else 'off'}")
        elif sub == "status":
            print(f"Game mode: {green('ON') if self.cfg['gamemode'] else yellow('off')}   "
                  f"auto-on-launch: {self.cfg['game_auto']}   governor: {self.cfg['governor']}   "
                  f"RAM: {self.ram_used()} MB")
        else:
            print("usage: gamemode on|off|auto|status   (no sudo needed)")
            return 1

    # ---- launching apps --------------------------------------------------
    def cmd_run(self, args):
        if not args:
            print("usage: run <installed app or game | file.exe>")
            return 1
        return self.run_app(args[0])

    def run_app(self, target):
        inst = self.winst_installed()
        kind, fps, name = "game", 60, target
        if target.lower().endswith(".exe"):
            if "proton-wind" not in inst:
                print(red(f"run: {target} is a Windows program.") +
                      " Install the compatibility layer:  sudo winst install proton-wind")
                return 127
            print(cyan("[proton-wind]") + f" translating Win32 calls for {target} ...")
        elif target in inst and inst[target]["kind"] in ("game", "app"):
            kind = inst[target]["kind"]
            fps = BASE_REPO.get(target, {}).get("fps", 60) or 60
        else:
            print(red(f"run: '{target}' is not installed") + dim(f"  (sudo winst install {target})"))
            return 127
        temp_gm = kind == "game" and self.cfg["game_auto"] and not self.cfg["gamemode"]
        if temp_gm:
            self.gm_on()
            print(dim("[gamemode] auto-enabled for this session"))
        print(f"Launching {bold(name)} ...")
        started = time.time()
        try:
            if kind == "game":
                boost = 1.18 if self.cfg["gamemode"] else 1.0
                samples = []
                for _ in range(6):
                    f = int(fps * boost * (0.96 + random.random() * 0.08))
                    samples.append(f)
                    ms = 1000 / f
                    sys.stdout.write(f"\r  {cyan('FPS')} {f:>4}   frametime {ms:5.2f} ms   "
                                     f"{'game mode ON ' if self.cfg['gamemode'] else 'game mode off'}")
                    sys.stdout.flush()
                    sleep(0.35)
                print(f"\n  session avg {sum(samples) // len(samples)} FPS, "
                      f"1% low {int(min(samples) * 0.93)} FPS")
            else:
                sleep(0.4)
                print(f"  {name} window opened and closed (simulated).")
        finally:
            if temp_gm:
                self.gm_off()
                print(dim("[gamemode] restored background services"))
        mins = (time.time() - started) / 60
        self.cfg["playtime"][name] = round(self.cfg["playtime"].get(name, 0) + mins, 3)
        self.cfg["recent"] = [name] + [r for r in self.cfg["recent"] if r != name][:7]
        self.save_cfg()
        return 0

    def cmd_fav(self, args):
        sub = args[0] if args else "list"
        if sub == "list":
            print(", ".join(self.cfg["favorites"]) or "no favorites yet")
        elif sub in ("add", "remove") and len(args) > 1:
            n = args[1]
            favs = self.cfg["favorites"]
            if sub == "add" and n in self.winst_installed() and n not in favs:
                favs.append(n)
            elif sub == "remove" and n in favs:
                favs.remove(n)
            self.save_cfg()
            print(f"favorites: {', '.join(favs) or '(none)'}")
        else:
            print("usage: fav list | add <name> | remove <name>")

    def cmd_reboot(self, args):
        if not self.elevated:
            print(red("reboot: Permission denied") + dim("  (try: sudo reboot)"))
            return 1
        print("Rebooting...")
        self.boot()
        self.t0 = time.time()

    # ---- the Hub: easy navigation ---------------------------------------
    def ask(self, p="> "):
        try:
            return input(p)
        except (EOFError, KeyboardInterrupt):
            print()
            return "q"

    def pause(self):
        self.ask(dim("  Press Enter... "))

    def apps(self):
        return {n: r for n, r in self.winst_installed().items() if r["kind"] in ("game", "app")}

    def all_items(self):
        items = [dict(name=n, desc=d, cat="system", builtin=True) for n, d in (
            ("files", "File browser"), ("settings", "System settings & services"),
            ("terminal", "Back to the terminal"), ("gamemode", "Toggle game mode"),
            ("store", "Package store (winst)"))]
        for n, r in self.apps().items():
            items.append(dict(name=n, desc=r["desc"], cat=r["category"], builtin=False))
        return items

    def search_items(self, q):
        q, scored = q.lower().strip(), []
        for it in self.all_items():
            nm, s = it["name"].lower(), 0
            hay = nm + " " + it["desc"].lower() + " " + it["cat"]
            if nm == q:
                s = 100
            elif nm.startswith(q):
                s = 80
            elif q in nm:
                s = 60
            elif q in hay:
                s = 40
            else:
                r = difflib.SequenceMatcher(None, q, nm).ratio()
                s = int(r * 40) if r > 0.55 else 0
            if s:
                scored.append((s, it))
        return [it for _, it in sorted(scored, key=lambda x: -x[0])]

    def launch_item(self, it):
        n = it["name"]
        if it["builtin"]:
            if n == "terminal":
                return "terminal"
            {"files": self.files_screen, "settings": self.system_screen, "store": self.store_screen,
             "gamemode": lambda: self.cmd_gamemode(["off" if self.cfg["gamemode"] else "on"])}[n]()
            if n == "gamemode":
                self.pause()
        else:
            self.run_app(n)
            self.pause()

    def cmd_go(self, args):
        if not args:
            print("usage: go <name>   e.g. 'go race'  (fuzzy)")
            return 1
        res = self.search_items(" ".join(args))
        if not res:
            print(red("go: nothing matches") + dim("  - try: winst search " + " ".join(args)))
            return 1
        if len(res) == 1 or res[0]["name"].startswith(args[0].lower()):
            return self.launch_item(res[0]) and 0
        for i, it in enumerate(res[:6], 1):
            print(f"  {i}) {it['name']:<18}{dim(it['desc'])}")
        c = self.ask("Open which? ")
        if c.isdigit() and 1 <= int(c) <= len(res[:6]):
            self.launch_item(res[int(c) - 1])

    def header(self, title):
        gm = green("● GAME MODE") if self.cfg["gamemode"] else dim("○ game mode off")
        now = datetime.datetime.now().strftime("%H:%M")
        print("\033[2J\033[H" if USE_COLOR else "\n" * 2, end="")
        print(bold(f"╭─ WindOS · {title} ") + dim("─" * max(2, 30 - len(title))) +
              f" {self.user['name']} · {now} · {gm} · {self.ram_used()} MB")
        print()

    def hub(self):
        while True:
            self.header("Hub")
            inst = self.apps()
            quick = []
            for n in self.cfg["favorites"] + self.cfg["recent"]:
                if n in inst and n not in quick:
                    quick.append(n)
            quick = quick[:9]
            if quick:
                print(cyan("  Jump back in"))
                for i, n in enumerate(quick, 1):
                    star = "★" if n in self.cfg["favorites"] else " "
                    print(f"   {i}) {star} {n:<18}{dim(inst[n]['desc'])}")
                print()
            print(f"  {bold('G')}ames   {bold('A')}pps   {bold('S')}tore   {bold('F')}iles   "
                  f"s{bold('Y')}stem   {bold('M')} game mode   {bold('T')}erminal   {bold('Q')}uit")
            print(dim("  or just type a name to search ('race', 'browser', 'edit' ...)\n"))
            ch = self.ask(cyan("  ▸ ")).strip()
            low = ch.lower()
            if not ch:
                continue
            if low in ("q", "quit", "exit"):
                return
            if low == "t":
                return
            elif low == "g":
                self.list_screen("game")
            elif low == "a":
                self.list_screen("app")
            elif low == "s":
                self.store_screen()
            elif low == "f":
                self.files_screen()
            elif low == "y":
                self.system_screen()
            elif low == "m":
                self.cmd_gamemode(["off" if self.cfg["gamemode"] else "on"])
                self.pause()
            elif ch.isdigit() and 1 <= int(ch) <= len(quick):
                self.run_app(quick[int(ch) - 1])
                self.pause()
            else:
                self.search_screen(ch.lstrip("/"))

    def cmd_wind(self, args):
        self.hub()

    def search_screen(self, q):
        res = self.search_items(q)[:9]
        self.header(f"Search: {q}")
        if not res:
            print(f"  Nothing installed matches '{q}'. Try the Store (S) or: winst search {q}")
            self.pause()
            return
        for i, it in enumerate(res, 1):
            print(f"   {i}) {it['name']:<18}{dim(it['desc'])}")
        c = self.ask(cyan("\n  number to open, Enter to go back ▸ ")).strip()
        if c.isdigit() and 1 <= int(c) <= len(res):
            if self.launch_item(res[int(c) - 1]) == "terminal":
                return

    def list_screen(self, kind):
        while True:
            self.header("Games" if kind == "game" else "Apps")
            items = [(n, r) for n, r in sorted(self.apps().items())
                     if (r["kind"] == "game") == (kind == "game")]
            if not items:
                print("  Nothing installed yet. Press B, then S for the Store.")
            for i, (n, r) in enumerate(items, 1):
                star = "★" if n in self.cfg["favorites"] else " "
                pt = self.cfg["playtime"].get(n)
                print(f"   {i}) {star} {n:<18}{dim(r['desc'])}" + (dim(f"  [{pt:.1f} min]") if pt else ""))
            c = self.ask(cyan("\n  number=launch · f<number>=favorite · b=back ▸ ")).strip().lower()
            if c in ("b", "q", ""):
                return
            if c.startswith("f") and c[1:].isdigit() and 1 <= int(c[1:]) <= len(items):
                n = items[int(c[1:]) - 1][0]
                favs = self.cfg["favorites"]
                favs.remove(n) if n in favs else favs.append(n)
                self.save_cfg()
            elif c.isdigit() and 1 <= int(c) <= len(items):
                self.run_app(items[int(c) - 1][0])
                self.pause()

    def store_screen(self):
        while True:
            self.winst.refresh()
            pk_, inst = self.winst.pkgs, self.winst.installed
            cats = sorted({m["category"] for m in pk_.values()})
            self.header("Store")
            up = self.winst.upgradable()
            for i, cat in enumerate(cats, 1):
                n_in = sum(1 for n, m in pk_.items() if m["category"] == cat and n in inst)
                tot = sum(1 for m in pk_.values() if m["category"] == cat)
                print(f"   {i}) {cat:<10}{dim(f'{n_in}/{tot} installed')}")
            print(f"\n  {bold('U')} update index   {bold('G')} upgrade all ({len(up)})   {bold('B')} back")
            c = self.ask(cyan("  ▸ ")).strip().lower()
            if c in ("b", "q", ""):
                return
            if c == "u":
                self.execute("sudo winst update")
                self.pause()
            elif c == "g":
                self.execute("sudo winst upgrade")
                self.pause()
            elif c.isdigit() and 1 <= int(c) <= len(cats):
                self.store_category(cats[int(c) - 1])

    def store_category(self, cat):
        while True:
            self.winst.refresh()
            pk_, inst = self.winst.pkgs, self.winst.installed
            items = sorted(n for n, m in pk_.items() if m["category"] == cat)
            self.header(f"Store · {cat}")
            for i, n in enumerate(items, 1):
                st = green("installed") if n in inst else dim("get      ")
                print(f"   {i}) {n:<18}{st}  {pk_[n]['version']:<8}{dim(pk_[n]['desc'])}")
            c = self.ask(cyan("\n  number=install/remove · b=back ▸ ")).strip().lower()
            if c in ("b", "q", ""):
                return
            if c.isdigit() and 1 <= int(c) <= len(items):
                n = items[int(c) - 1]
                self.execute(f"sudo winst {'remove' if n in inst else 'install'} {n}")
                self.pause()

    def files_screen(self):
        v = self.cwd
        while True:
            self.header("Files")
            h = hpath(v)
            entries = sorted(h.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))[:40]
            print(f"  {bold(v)}\n")
            print("   0) ..  (up)")
            for i, e in enumerate(entries, 1):
                size = "" if e.is_dir() else dim(f"  {e.stat().st_size} B")
                print(f"   {i}) {self.fmt_name(e)}{size}")
            c = self.ask(cyan("\n  number=open · 0=up · b=back ▸ ")).strip().lower()
            if c in ("b", "q", ""):
                return
            if c == "0":
                v = self.vresolve(v + "/..")
            elif c.isdigit() and 1 <= int(c) <= len(entries):
                e = entries[int(c) - 1]
                if e.is_dir():
                    v = self.vresolve(v + "/" + e.name)
                else:
                    vp = self.vresolve(v + "/" + e.name)
                    print()
                    if vp == PROTECTED_USERS_FILE and not self.elevated:
                        print(red("  Permission denied"))
                    else:
                        print(dim("  " + "─" * 30))
                        for line in e.read_text(encoding="utf-8", errors="replace").splitlines()[:15]:
                            print("  " + line)
                    self.pause()

    def system_screen(self):
        while True:
            self.header("System")
            self.cmd_windfetch([])
            up = self.winst.upgradable() if hasattr(self.winst, "pkgs") else []
            print(f"\n  {bold('M')} toggle game mode   {bold('V')} services   {bold('U')} check updates   {bold('B')} back")
            c = self.ask(cyan("  ▸ ")).strip().lower()
            if c in ("b", "q", ""):
                return
            if c == "m":
                self.cmd_gamemode(["off" if self.cfg["gamemode"] else "on"])
                self.pause()
            elif c == "v":
                print()
                self.cmd_winctl(["list"])
                self.pause()
            elif c == "u":
                self.execute("sudo winst update")
                self.pause()

    # ---- main loop -------------------------------------------------------
    def prompt_str(self):
        u = self.user["name"]
        return (f"{green(u + '@' + self.cfg['hostname'])}:{cyan(self.short_cwd())}$ ")

    def repl(self):
        try:
            import readline  # noqa
            cmds = sorted(n[4:] for n in dir(self) if n.startswith("cmd_")) + list(ALIASES)
            readline.set_completer(lambda t, i: ([c for c in cmds if c.startswith(t)] + [None])[i])
            readline.parse_and_bind("tab: complete")
        except ImportError:
            pass
        print(f"Welcome to {bold('WindOS ' + VERSION)} ({CODENAME}).  Type {cyan('wind')} for the Hub, "
              f"{cyan('help')} for commands.\n")
        while self.running:
            try:
                line = input(self.prompt_str())
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                print()
                continue
            self.execute(line)

    def cmd_exit(self, args):
        self.running = False
        print("Shutting down WindOS... bye.")


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="WindOS emulation layer")
    ap.add_argument("--root", help="virtual root directory (default ~/.windos)")
    ap.add_argument("--reset", action="store_true", help="wipe the virtual root and start over")
    ap.add_argument("-c", "--command", help="run commands (separated by ;) then exit")
    args = ap.parse_args()
    if args.root:
        set_root(args.root)
    if args.reset:
        if ROOT.exists() and input(f"Delete {ROOT}? type 'yes': ").strip() == "yes":
            shutil.rmtree(ROOT)
            print("Wiped.")
        return
    sh = Shell()
    if not USERS_F.exists():
        sh.first_boot()
    sh.load_state()
    if not sh.login():
        print("Too many failed attempts.")
        return 1
    sh.boot()
    if args.command:
        for part in args.command.split(";"):
            sh.execute(part)
        return 0
    sh.repl()
    return 0


if __name__ == "__main__":
    sys.exit(main())
