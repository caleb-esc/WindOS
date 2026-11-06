"""PySide6 desktop shell for WindOS. Run with: python -m windos.desktop.app"""
from __future__ import annotations
import contextlib
import io
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFont, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QDialog, QFormLayout, QLineEdit, QMainWindow, QMessageBox,
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTextEdit,
    QTreeWidget, QTreeWidgetItem, QTabWidget, QStatusBar
)

from windos.core import engine
from windos.core.auth import authenticate


class LoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WindOS — Sign in")
        self.setFixedWidth(380)
        layout = QVBoxLayout(self)
        title = QLabel("WindOS")
        title.setObjectName("brand")
        subtitle = QLabel("Sign in to your WindOS session")
        self.username = QLineEdit()
        self.username.setPlaceholderText("Username")
        self.password = QLineEdit()
        self.password.setPlaceholderText("Password")
        self.password.setEchoMode(QLineEdit.Password)
        form = QFormLayout()
        form.addRow("Username", self.username)
        form.addRow("Password", self.password)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(form)
        self.error = QLabel("")
        self.error.setStyleSheet("color:#ff7777")
        layout.addWidget(self.error)
        button = QPushButton("Sign in")
        button.clicked.connect(self.try_login)
        self.password.returnPressed.connect(self.try_login)
        layout.addWidget(button)
        self.user = None

    def try_login(self):
        user = authenticate(self.username.text().strip(), self.password.text())
        if user:
            self.user = user
            self.accept()
        else:
            self.error.setText("Incorrect username or password.")


class WindDesktop(QMainWindow):
    def __init__(self, user):
        super().__init__()
        self.user = user
        self.shell = engine.Shell()
        self.shell.load_state()
        self.shell.user = user
        self.shell.cwd = user.get("home", "/")
        self.shell.running = True
        self.setWindowTitle(f"WindOS Desktop — {user['name']}")
        self.resize(1120, 740)
        self.setMinimumSize(780, 520)

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 8)
        top = QHBoxLayout()
        brand = QLabel("WindOS")
        brand.setObjectName("brand")
        top.addWidget(brand)
        top.addStretch()
        self.user_label = QLabel(f"{user['name']}  •  {self.shell.cfg.get('hostname', 'windos')}")
        top.addWidget(self.user_label)
        root.addLayout(top)

        self.tabs = QTabWidget()
        self.terminal = QTextEdit()
        self.terminal.setReadOnly(True)
        self.terminal.setFont(QFont("DejaVu Sans Mono", 10))
        self.terminal.setPlaceholderText("WindOS terminal output")
        terminal_page = QWidget()
        tl = QVBoxLayout(terminal_page)
        self.command = QLineEdit()
        self.command.setPlaceholderText("Enter a WindOS command… (try help, windfetch, winst list)")
        self.command.returnPressed.connect(self.run_command)
        tl.addWidget(self.terminal)
        tl.addWidget(self.command)
        self.tabs.addTab(terminal_page, "Terminal")

        files_page = QWidget()
        fl = QVBoxLayout(files_page)
        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderLabels(["Virtual filesystem", "Type"])
        refresh = QPushButton("Refresh files")
        refresh.clicked.connect(self.refresh_files)
        fl.addWidget(refresh)
        fl.addWidget(self.file_tree)
        self.tabs.addTab(files_page, "Files")

        system_page = QWidget()
        sl = QVBoxLayout(system_page)
        self.system_info = QLabel()
        self.system_info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        sl.addWidget(self.system_info)
        gm = QPushButton("Toggle Game Mode")
        gm.clicked.connect(self.toggle_gamemode)
        sl.addWidget(gm)
        sl.addStretch()
        self.tabs.addTab(system_page, "System")
        root.addWidget(self.tabs)
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("WindOS session authenticated")

        logout = QAction("Log out", self)
        logout.triggered.connect(self.close)
        self.menuBar().addAction(logout)
        self.refresh_files()
        self.refresh_system()
        self.append("Welcome to WindOS Desktop. Type 'help' to see available commands.\n")

    def append(self, text):
        self.terminal.moveCursor(QTextCursor.End)
        self.terminal.insertPlainText(text)
        self.terminal.ensureCursorVisible()

    def run_command(self):
        line = self.command.text().strip()
        self.command.clear()
        if not line:
            return
        output = io.StringIO()
        try:
            with contextlib.redirect_stdout(output):
                self.shell.execute(line)
        except Exception as exc:
            output.write(f"WindOS error: {exc}\n")
        result = output.getvalue()
        self.append(f"{self.user['name']}@{self.shell.cfg.get('hostname','windos')}:{self.shell.short_cwd()}$ {line}\n{result}")
        self.refresh_files()
        self.refresh_system()

    def refresh_files(self):
        self.file_tree.clear()
        root = QTreeWidgetItem(["/", "directory"])
        self.file_tree.addTopLevelItem(root)
        def add_children(parent, host_path, depth=0):
            if depth > 4:
                return
            try:
                entries = sorted(host_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            except (OSError, PermissionError):
                return
            for path in entries[:250]:
                item = QTreeWidgetItem([path.name, "directory" if path.is_dir() else "file"])
                parent.addChild(item)
                if path.is_dir():
                    add_children(item, path, depth + 1)
        add_children(root, engine.ROOT)
        root.setExpanded(True)

    def refresh_system(self):
        services = sum(1 for s in self.shell.svc.values() if s.get("running"))
        self.system_info.setText(
            f"<h2>System overview</h2><p><b>Hostname:</b> {self.shell.cfg.get('hostname','windos')}</p>"
            f"<p><b>Signed in:</b> {self.user['name']}</p>"
            f"<p><b>Game Mode:</b> {'ON' if self.shell.cfg.get('gamemode') else 'OFF'}</p>"
            f"<p><b>Services running:</b> {services}/{len(self.shell.svc)}</p>"
            f"<p><b>Reported RAM:</b> {self.shell.ram_used()} MB</p>"
            f"<p><b>Virtual root:</b> {engine.ROOT}</p>"
        )

    def toggle_gamemode(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.shell.execute("gamemode off" if self.shell.cfg.get("gamemode") else "gamemode on")
        self.append(output.getvalue())
        self.refresh_system()


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet("""
      QMainWindow,QDialog,QWidget { background:#111827; color:#e5e7eb; }
      QMenuBar,QMenu { background:#172033; color:#e5e7eb; }
      QTabWidget::pane { border:1px solid #334155; }
      QTabBar::tab { background:#1e293b; padding:10px 18px; }
      QTabBar::tab:selected { background:#26364e; }
      QLineEdit,QTextEdit,QTreeWidget { background:#0b1220; color:#e5e7eb; border:1px solid #334155; padding:8px; }
      QPushButton { background:#2563eb; color:white; border:0; border-radius:6px; padding:9px 14px; }
      QPushButton:hover { background:#1d4ed8; }
      QLabel#brand { color:#60a5fa; font-size:25px; font-weight:700; }
      QStatusBar { background:#172033; }
    """)
    if not engine.USERS_F.exists():
        QMessageBox.information(None, "First boot required", "No WindOS account exists yet. Run 'python -m windos.cli' once in a terminal to create the first account.")
        return 2
    dialog = LoginDialog()
    if dialog.exec() != QDialog.Accepted:
        return 0
    window = WindDesktop(dialog.user)
    window.show()
    return app.exec()

if __name__ == "__main__":
    raise SystemExit(main())
