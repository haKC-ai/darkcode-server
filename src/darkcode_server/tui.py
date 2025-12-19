"""TUI interface for DarkCode Server using pyTermTk."""

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, List, Callable

import TermTk as ttk

from darkcode_server import __version__
from darkcode_server.config import ServerConfig


def show_banner():
    """Show the DarkCode banner using hakcer."""
    try:
        from hakcer import show_banner as hakcer_banner, set_theme

        set_theme("synthwave")

        # Try custom banner file locations
        banner_paths = [
            Path("/Users/0xdeadbeef/Desktop/darkcode.txt"),  # Primary custom
            Path.home() / "darkcode" / ".darkcode" / "banner.txt",
            Path(__file__).parent / "assets" / "banner.txt",
        ]

        banner_file = next((p for p in banner_paths if p.exists()), None)

        if banner_file:
            hakcer_banner(
                custom_file=str(banner_file),
                effect_name="rain",
                hold_time=2.0,
            )
        else:
            # Fallback to text
            hakcer_banner(
                text="DARKCODE",
                effect_name="glitch",
                hold_time=1.0,
            )
        return True
    except ImportError:
        return False
    except Exception:
        return False


class SystemCheck:
    """Check system requirements."""

    def __init__(self):
        self.results = {}

    def check_claude_code(self) -> tuple[bool, str]:
        """Check if Claude Code CLI is installed."""
        if shutil.which("claude"):
            try:
                result = subprocess.run(
                    ["claude", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    version = result.stdout.strip().split()[-1] if result.stdout else "unknown"
                    return True, f"v{version}"
            except Exception:
                pass
        return False, "Not installed"

    def check_tailscale(self) -> tuple[bool, str]:
        """Check if Tailscale is available and connected."""
        if shutil.which("tailscale"):
            try:
                result = subprocess.run(
                    ["tailscale", "status", "--json"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    import json
                    data = json.loads(result.stdout)
                    if data.get("Self", {}).get("Online"):
                        ip = data.get("TailscaleIPs", [""])[0]
                        return True, f"Connected ({ip})"
                    return False, "Not connected"
            except Exception:
                pass
            return False, "Not running"
        return False, "Not installed"

    def is_tailscale_installed(self) -> bool:
        """Check if Tailscale binary exists."""
        return shutil.which("tailscale") is not None

    def check_python_version(self) -> tuple[bool, str]:
        """Check Python version."""
        version = sys.version_info
        if version >= (3, 9):
            return True, f"{version.major}.{version.minor}.{version.micro}"
        return False, f"{version.major}.{version.minor} (need 3.9+)"

    def check_working_dir(self, config: ServerConfig) -> tuple[bool, str]:
        """Check if working directory exists and is accessible."""
        if config.working_dir.exists():
            if config.working_dir.is_dir():
                path_str = str(config.working_dir)
                if len(path_str) > 30:
                    path_str = "..." + path_str[-27:]
                return True, path_str
            return False, "Not a directory"
        return False, "Not found"

    def run_all(self, config: ServerConfig) -> dict:
        """Run all system checks."""
        self.results = {
            "Python": self.check_python_version(),
            "Claude Code": self.check_claude_code(),
            "Tailscale": self.check_tailscale(),
            "Working Dir": self.check_working_dir(config),
        }
        return self.results


# Compact banner for TUI (fits better in terminal)
BANNER_COMPACT = r"""
    ██████╗  █████╗ ██████╗ ██╗  ██╗ ██████╗ ██████╗ ██████╗ ███████╗
    ██╔══██╗██╔══██╗██╔══██╗██║ ██╔╝██╔════╝██╔═══██╗██╔══██╗██╔════╝
    ██║  ██║███████║██████╔╝█████╔╝ ██║     ██║   ██║██║  ██║█████╗
    ██║  ██║██╔══██║██╔══██╗██╔═██╗ ██║     ██║   ██║██║  ██║██╔══╝
    ██████╔╝██║  ██║██║  ██║██║  ██╗╚██████╗╚██████╔╝██████╔╝███████╗
    ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝
"""


class CommandPalette(ttk.TTkWindow):
    """Command palette popup (Ctrl+P)."""

    commandSelected = ttk.pyTTkSignal(str)

    def __init__(self, commands: List[tuple], parent=None):
        super().__init__(
            parent=parent,
            title=" Command Palette (Ctrl+P) ",
            pos=(10, 5),
            size=(60, 20),
            border=True,
            layout=ttk.TTkVBoxLayout()
        )

        self._commands = commands
        self._filtered = list(commands)

        # Search input
        self._search = ttk.TTkLineEdit()
        self._search.textEdited.connect(self._filter_commands)
        self.layout().addWidget(ttk.TTkLabel(text="Search commands:", maxHeight=1))
        self.layout().addWidget(self._search)

        # Results list
        self._list = ttk.TTkList(minHeight=12)
        self._update_list()
        self._list.textClicked.connect(self._on_select)
        self.layout().addWidget(self._list)

        # Hint
        hint = ttk.TTkString(" Enter: select | Esc: close", ttk.TTkColor.fg('#666666'))
        self.layout().addWidget(ttk.TTkLabel(text=hint, maxHeight=1))

        self._search.setFocus()

    def _filter_commands(self, text):
        """Filter commands based on search text."""
        query = str(text).lower()
        if query:
            self._filtered = [
                (key, title, hotkey) for key, title, hotkey in self._commands
                if query in title.lower() or query in key.lower()
            ]
        else:
            self._filtered = list(self._commands)
        self._update_list()

    def _update_list(self):
        """Update the command list."""
        self._list.clear()
        for key, title, hotkey in self._filtered:
            if hotkey:
                item = f"  {title}  [{hotkey}]"
            else:
                item = f"  {title}"
            self._list.addItem(item)

    def _on_select(self, text):
        """Handle command selection."""
        text_str = str(text).strip()
        for key, title, hotkey in self._filtered:
            if title in text_str:
                self.commandSelected.emit(key)
                self.close()
                break

    def keyEvent(self, evt):
        """Handle key events."""
        if evt.key == ttk.TTkK.Key_Escape:
            self.close()
            return True
        if evt.key == ttk.TTkK.Key_Enter:
            # Select first item
            if self._filtered:
                self.commandSelected.emit(self._filtered[0][0])
                self.close()
            return True
        return super().keyEvent(evt)


class DarkCodeTUI:
    """Main TUI application using pyTermTk with full navigation."""

    def __init__(self, config: Optional[ServerConfig] = None):
        self.config = config or ServerConfig.load()
        self.system_check = SystemCheck()
        self.result = None
        self.root = None
        self.menu_list = None
        self.sidebar_list = None
        self.content_stack = None
        self.selected_index = 0
        self.active_panel = "sidebar"  # "sidebar", "menu", "status"
        self.panels = []  # List of focusable panels
        self.current_panel_idx = 0
        self.command_palette = None

        # Menu items: (key, title, mode/action, hotkey)
        self._menu_items = [
            ("start_direct", "Start Server (Direct LAN)", "direct", "1"),
            ("start_tailscale", "Start Server (Tailscale)", "tailscale", "2"),
            ("start_ssh", "Start Server (SSH Tunnel)", "ssh", "3"),
            ("status", "Server Status", None, "s"),
            ("qr", "Show QR Code", None, "q"),
            ("guest", "Guest Codes", None, "g"),
            ("config", "Configuration", None, "c"),
            ("security", "Security Settings", None, "x"),
            ("setup", "Setup Wizard", None, "w"),
            ("quit", "Quit", None, "Q"),
        ]

        # Sidebar sections
        self._sidebar_items = [
            ("server", "Server", "server"),
            ("tools", "Tools", "tools"),
            ("settings", "Settings", "settings"),
        ]

        # Commands for palette
        self._all_commands = [
            (key, title, hotkey) for key, title, _, hotkey in self._menu_items
        ] + [
            ("help", "Show Help", "?"),
            ("refresh", "Refresh Status", "r"),
            ("toggle_logs", "Toggle Logs Panel", "l"),
        ]

    def _get_banner_text(self) -> str:
        """Get the banner text."""
        # Try to load from file first
        banner_paths = [
            Path("/Users/0xdeadbeef/Desktop/tui_banner.txt"),
            Path.home() / "darkcode" / ".darkcode" / "tui_banner.txt",
        ]

        for path in banner_paths:
            if path.exists():
                try:
                    return path.read_text().strip()
                except Exception:
                    pass

        return BANNER_COMPACT.strip()

    def _execute_command(self, key: str):
        """Execute a command by key."""
        if key == "quit":
            self.root.quit()
        elif key == "help":
            self._show_help()
        elif key == "refresh":
            self._refresh_status()
        elif key == "start_tailscale":
            if not self.system_check.is_tailscale_installed():
                self.result = ("install_tailscale", None)
            else:
                self.result = ("start", "tailscale")
            self.root.quit()
        elif key.startswith("start_"):
            mode = key.replace("start_", "")
            self.result = ("start", mode)
            self.root.quit()
        else:
            self.result = (key, None)
            self.root.quit()

    def _show_command_palette(self):
        """Show the command palette."""
        if self.command_palette:
            self.command_palette.close()

        self.command_palette = CommandPalette(self._all_commands, parent=self.root)
        self.command_palette.commandSelected.connect(self._execute_command)
        self.command_palette.show()

    def _show_help(self):
        """Show help window."""
        help_win = ttk.TTkWindow(
            parent=self.root,
            title=" Keyboard Shortcuts ",
            pos=(15, 3),
            size=(50, 18),
            border=True,
            layout=ttk.TTkVBoxLayout()
        )

        shortcuts = [
            ("Navigation", [
                ("Tab / Shift+Tab", "Switch panels"),
                ("Arrow Keys", "Navigate items"),
                ("Enter", "Select/Execute"),
                ("Escape", "Close popup/Cancel"),
            ]),
            ("Commands", [
                ("Ctrl+P", "Command Palette"),
                ("1-3", "Start Server modes"),
                ("q", "Show QR Code"),
                ("s", "Server Status"),
                ("c", "Configuration"),
                ("Q", "Quit"),
            ]),
            ("Panels", [
                ("r", "Refresh Status"),
                ("l", "Toggle Logs"),
                ("?", "Show Help"),
            ]),
        ]

        for section, items in shortcuts:
            help_win.layout().addWidget(ttk.TTkLabel(
                text=ttk.TTkString(f" {section}", ttk.TTkColor.fg('#ffaa00') + ttk.TTkColor.BOLD),
                maxHeight=1
            ))
            for key, desc in items:
                text = ttk.TTkString(f"   {key:<18}", ttk.TTkColor.fg('#00ff88')) + \
                       ttk.TTkString(desc, ttk.TTkColor.fg('#aaaaaa'))
                help_win.layout().addWidget(ttk.TTkLabel(text=text, maxHeight=1))

        help_win.layout().addWidget(ttk.TTkSpacer())
        hint = ttk.TTkString(" Press Escape to close", ttk.TTkColor.fg('#666666'))
        help_win.layout().addWidget(ttk.TTkLabel(text=hint, maxHeight=1))

        help_win.show()

    def _refresh_status(self):
        """Refresh system status (placeholder - would update status panel)."""
        self.system_check.run_all(self.config)
        # In a real implementation, would update the status widgets

    def _switch_panel(self, direction: int = 1):
        """Switch focus between panels."""
        if not self.panels:
            return

        self.current_panel_idx = (self.current_panel_idx + direction) % len(self.panels)
        panel = self.panels[self.current_panel_idx]
        panel.setFocus()

    def _handle_global_key(self, evt) -> bool:
        """Handle global keyboard shortcuts."""
        key = evt.key
        mod = evt.mod

        # Ctrl+P - Command Palette
        if mod == ttk.TTkK.ControlModifier and key == ttk.TTkK.Key_P:
            self._show_command_palette()
            return True

        # Tab - Switch panels
        if key == ttk.TTkK.Key_Tab:
            direction = -1 if mod == ttk.TTkK.ShiftModifier else 1
            self._switch_panel(direction)
            return True

        # Escape - Close popups
        if key == ttk.TTkK.Key_Escape:
            if self.command_palette:
                self.command_palette.close()
                self.command_palette = None
                return True

        # ? - Help
        if key == ttk.TTkK.Key_Question:
            self._show_help()
            return True

        # Hotkey shortcuts
        key_char = chr(key) if 32 <= key <= 126 else None
        if key_char:
            for cmd_key, title, hotkey in self._all_commands:
                if hotkey and hotkey == key_char:
                    self._execute_command(cmd_key)
                    return True

        return False

    def _create_menu_bar(self) -> ttk.TTkFrame:
        """Create the menu bar."""
        menu_bar = ttk.TTkFrame(border=False, maxHeight=1)
        menu_layout = ttk.TTkHBoxLayout()
        menu_bar.setLayout(menu_layout)

        # File menu
        file_btn = ttk.TTkButton(text=" File ", border=False, maxWidth=8)
        file_btn.clicked.connect(lambda: self._show_file_menu())
        menu_layout.addWidget(file_btn)

        # View menu
        view_btn = ttk.TTkButton(text=" View ", border=False, maxWidth=8)
        view_btn.clicked.connect(lambda: self._show_view_menu())
        menu_layout.addWidget(view_btn)

        # Server menu
        server_btn = ttk.TTkButton(text=" Server ", border=False, maxWidth=10)
        server_btn.clicked.connect(lambda: self._show_server_menu())
        menu_layout.addWidget(server_btn)

        # Help menu
        help_btn = ttk.TTkButton(text=" Help ", border=False, maxWidth=8)
        help_btn.clicked.connect(lambda: self._show_help())
        menu_layout.addWidget(help_btn)

        menu_layout.addWidget(ttk.TTkSpacer())

        # Right side: version
        version_label = ttk.TTkLabel(
            text=ttk.TTkString(f"v{__version__} ", ttk.TTkColor.fg('#666666')),
            maxWidth=15
        )
        menu_layout.addWidget(version_label)

        return menu_bar

    def _show_file_menu(self):
        """Show File dropdown menu."""
        menu = ttk.TTkWindow(
            parent=self.root,
            title="",
            pos=(1, 1),
            size=(25, 8),
            border=True,
            layout=ttk.TTkVBoxLayout()
        )

        items = [
            ("New Session", "config"),
            ("Open Working Dir", "open_dir"),
            ("─" * 20, None),
            ("Quit", "quit"),
        ]

        for label, cmd in items:
            if cmd is None:
                menu.layout().addWidget(ttk.TTkLabel(text=label, maxHeight=1))
            else:
                btn = ttk.TTkButton(text=f" {label}", border=False, maxHeight=1)
                btn.clicked.connect(lambda c=cmd: (menu.close(), self._execute_command(c)))
                menu.layout().addWidget(btn)

        menu.show()

    def _show_view_menu(self):
        """Show View dropdown menu."""
        menu = ttk.TTkWindow(
            parent=self.root,
            title="",
            pos=(9, 1),
            size=(25, 8),
            border=True,
            layout=ttk.TTkVBoxLayout()
        )

        items = [
            ("Refresh Status [r]", "refresh"),
            ("Show QR Code [q]", "qr"),
            ("─" * 20, None),
            ("Command Palette [^P]", "palette"),
        ]

        for label, cmd in items:
            if cmd is None:
                menu.layout().addWidget(ttk.TTkLabel(text=label, maxHeight=1))
            elif cmd == "palette":
                btn = ttk.TTkButton(text=f" {label}", border=False, maxHeight=1)
                btn.clicked.connect(lambda: (menu.close(), self._show_command_palette()))
                menu.layout().addWidget(btn)
            else:
                btn = ttk.TTkButton(text=f" {label}", border=False, maxHeight=1)
                btn.clicked.connect(lambda c=cmd: (menu.close(), self._execute_command(c)))
                menu.layout().addWidget(btn)

        menu.show()

    def _show_server_menu(self):
        """Show Server dropdown menu."""
        menu = ttk.TTkWindow(
            parent=self.root,
            title="",
            pos=(17, 1),
            size=(30, 10),
            border=True,
            layout=ttk.TTkVBoxLayout()
        )

        items = [
            ("Start (Direct LAN) [1]", "start_direct"),
            ("Start (Tailscale) [2]", "start_tailscale"),
            ("Start (SSH Tunnel) [3]", "start_ssh"),
            ("─" * 25, None),
            ("Status [s]", "status"),
            ("Guest Codes [g]", "guest"),
        ]

        for label, cmd in items:
            if cmd is None:
                menu.layout().addWidget(ttk.TTkLabel(text=label, maxHeight=1))
            else:
                btn = ttk.TTkButton(text=f" {label}", border=False, maxHeight=1)
                btn.clicked.connect(lambda c=cmd: (menu.close(), self._execute_command(c)))
                menu.layout().addWidget(btn)

        menu.show()

    def _create_sidebar(self) -> ttk.TTkFrame:
        """Create the sidebar navigation."""
        sidebar = ttk.TTkFrame(
            title=" Navigation ",
            border=True,
            minWidth=20,
            maxWidth=22
        )
        sidebar_layout = ttk.TTkVBoxLayout()
        sidebar.setLayout(sidebar_layout)

        self.sidebar_list = ttk.TTkList(minHeight=8)

        sections = [
            ("▶ Server", "server"),
            ("  ├ Start Direct", "start_direct"),
            ("  ├ Start Tailscale", "start_tailscale"),
            ("  └ Start SSH", "start_ssh"),
            ("", None),
            ("⚙ Tools", "tools"),
            ("  ├ QR Code", "qr"),
            ("  ├ Guest Codes", "guest"),
            ("  └ Status", "status"),
            ("", None),
            ("◆ Settings", "settings"),
            ("  ├ Config", "config"),
            ("  ├ Security", "security"),
            ("  └ Setup", "setup"),
        ]

        for label, cmd in sections:
            self.sidebar_list.addItem(label if label else " ")

        @ttk.pyTTkSlot(str)
        def _on_sidebar_click(text):
            text_str = str(text).strip()
            for label, cmd in sections:
                if cmd and label.strip() in text_str or text_str in label:
                    self._execute_command(cmd)
                    break

        self.sidebar_list.textClicked.connect(_on_sidebar_click)
        sidebar_layout.addWidget(self.sidebar_list)

        # Hotkeys hint
        hint = ttk.TTkString("Tab: switch", ttk.TTkColor.fg('#555555'))
        sidebar_layout.addWidget(ttk.TTkLabel(text=hint, maxHeight=1))

        return sidebar

    def _create_status_panel(self) -> ttk.TTkFrame:
        """Create the system status panel."""
        status_frame = ttk.TTkFrame(
            title=" System Status ",
            border=True,
            minWidth=40,
            maxWidth=50
        )
        status_layout = ttk.TTkVBoxLayout()
        status_frame.setLayout(status_layout)

        status_layout.addWidget(ttk.TTkSpacer())

        checks = self.system_check.run_all(self.config)
        for name, (ok, msg) in checks.items():
            icon = "●" if ok else "○"
            icon_color = ttk.TTkColor.fg('#00ff88') if ok else ttk.TTkColor.fg('#ff4466')
            label_color = ttk.TTkColor.fg('#ffffff')
            value_color = ttk.TTkColor.fg('#aaaaaa')

            text = (
                ttk.TTkString(f"  {icon} ", icon_color) +
                ttk.TTkString(f"{name}: ", label_color) +
                ttk.TTkString(msg, value_color)
            )
            status_layout.addWidget(ttk.TTkLabel(text=text, maxHeight=1))

        # Network info
        status_layout.addWidget(ttk.TTkLabel(text="", maxHeight=1))
        status_layout.addWidget(ttk.TTkLabel(
            text=ttk.TTkString("  Network:", ttk.TTkColor.fg('#ffaa00')),
            maxHeight=1
        ))

        ips = self.config.get_local_ips()
        if ips:
            for ip_info in ips[:3]:
                text = ttk.TTkString(
                    f"    {ip_info['name']}: {ip_info['address']}",
                    ttk.TTkColor.fg('#888888')
                )
                status_layout.addWidget(ttk.TTkLabel(text=text, maxHeight=1))

        tailscale_ip = self.config.get_tailscale_ip()
        if tailscale_ip:
            text = ttk.TTkString(f"    tailscale: {tailscale_ip}", ttk.TTkColor.fg('#00aaff'))
            status_layout.addWidget(ttk.TTkLabel(text=text, maxHeight=1))

        status_layout.addWidget(ttk.TTkSpacer())
        return status_frame

    def _create_main_menu(self) -> ttk.TTkFrame:
        """Create the main menu panel."""
        menu_frame = ttk.TTkFrame(
            title=" Quick Actions ",
            border=True,
            minWidth=40
        )
        menu_layout = ttk.TTkVBoxLayout()
        menu_frame.setLayout(menu_layout)

        # Instructions
        hint = ttk.TTkString(
            "  ↑↓ Navigate │ Enter Select │ Ctrl+P Palette",
            ttk.TTkColor.fg('#666666')
        )
        menu_layout.addWidget(ttk.TTkLabel(text=hint, maxHeight=1))
        menu_layout.addWidget(ttk.TTkLabel(text="", maxHeight=1))

        # Menu list widget
        self.menu_list = ttk.TTkList(minHeight=12)

        # Add menu items with hotkeys
        for i, (key, title, mode, hotkey) in enumerate(self._menu_items):
            # Add section separators
            if key == "status":
                self.menu_list.addItem("───────────────────────────")
            elif key == "config":
                self.menu_list.addItem("───────────────────────────")
            elif key == "quit":
                self.menu_list.addItem("───────────────────────────")

            # Icon based on action type
            if key.startswith("start_"):
                icon = "▶"
            elif key == "quit":
                icon = "✕"
            elif key == "qr":
                icon = "◫"
            elif key == "security":
                icon = "◆"
            elif key == "config":
                icon = "⚙"
            elif key == "setup":
                icon = "★"
            else:
                icon = "›"

            # Show hotkey
            hotkey_str = f"[{hotkey}]" if hotkey else ""
            self.menu_list.addItem(f"  {icon}  {title}  {hotkey_str}")

        # Connect click signal
        @ttk.pyTTkSlot(str)
        def _on_menu_click(text):
            text_str = str(text).strip()
            if text_str.startswith("─"):
                return
            for key, title, mode, hotkey in self._menu_items:
                if title in text_str:
                    self._execute_command(key)
                    break

        self.menu_list.textClicked.connect(_on_menu_click)
        menu_layout.addWidget(self.menu_list)

        return menu_frame

    def run(self) -> Optional[tuple]:
        """Run the TUI application."""
        try:
            # Create the main TTk application
            self.root = ttk.TTk(
                title="DarkCode Server",
                sigmask=(
                    ttk.TTkTerm.Sigmask.CTRL_C |
                    ttk.TTkTerm.Sigmask.CTRL_S |
                    ttk.TTkTerm.Sigmask.CTRL_Z
                )
            )

            # Install global key handler
            original_key_event = self.root.keyEvent

            def custom_key_event(evt):
                if self._handle_global_key(evt):
                    return True
                return original_key_event(evt)

            self.root.keyEvent = custom_key_event

            # Main vertical layout
            main_layout = ttk.TTkVBoxLayout()
            self.root.setLayout(main_layout)

            # === MENU BAR ===
            menu_bar = self._create_menu_bar()
            main_layout.addWidget(menu_bar)

            # === HEADER: Banner ===
            banner_text = self._get_banner_text()
            banner_lines = banner_text.split('\n')

            # Color gradient (magenta -> cyan)
            gradient = [
                '#ff00ff', '#ee11ff', '#dd22ff', '#cc33ff', '#bb44ff',
                '#aa55ff', '#9966ff', '#8877ff', '#7788ee', '#6699dd',
                '#55aacc', '#44bbbb', '#33ccaa', '#22dd99', '#11ee88',
                '#00ff77', '#00ff88', '#00ffaa', '#00ffcc',
            ]

            # Create banner frame
            banner_frame = ttk.TTkFrame(border=False, maxHeight=len(banner_lines) + 1)
            banner_layout = ttk.TTkVBoxLayout()
            banner_frame.setLayout(banner_layout)

            for i, line in enumerate(banner_lines[:20]):
                color_hex = gradient[min(i, len(gradient) - 1)]
                color = ttk.TTkColor.fg(color_hex)
                label = ttk.TTkLabel(text=ttk.TTkString(line, color), maxHeight=1)
                banner_layout.addWidget(label)

            main_layout.addWidget(banner_frame)

            # Separator
            main_layout.addWidget(ttk.TTkLabel(
                text=ttk.TTkString("─" * 100, ttk.TTkColor.fg('#444444')),
                maxHeight=1
            ))

            # === MAIN CONTENT: Three-column layout ===
            content_frame = ttk.TTkFrame(border=False)
            content_layout = ttk.TTkHBoxLayout()
            content_frame.setLayout(content_layout)

            # --- LEFT: Sidebar Navigation ---
            sidebar = self._create_sidebar()
            content_layout.addWidget(sidebar)
            self.panels.append(self.sidebar_list)

            # --- MIDDLE: Status Panel ---
            status_panel = self._create_status_panel()
            content_layout.addWidget(status_panel)

            # --- RIGHT: Main Menu ---
            main_menu = self._create_main_menu()
            content_layout.addWidget(main_menu)
            self.panels.append(self.menu_list)

            main_layout.addWidget(content_frame)

            # === FOOTER / STATUS BAR ===
            footer_frame = ttk.TTkFrame(border=False, maxHeight=1)
            footer_layout = ttk.TTkHBoxLayout()
            footer_frame.setLayout(footer_layout)

            # Left: hints
            left_hint = ttk.TTkString(
                " Tab: panels │ ↑↓: navigate │ Enter: select │ Ctrl+P: commands │ ?: help",
                ttk.TTkColor.fg('#555555')
            )
            footer_layout.addWidget(ttk.TTkLabel(text=left_hint))

            footer_layout.addWidget(ttk.TTkSpacer())

            # Right: quit hint
            right_hint = ttk.TTkString(" Q: quit ", ttk.TTkColor.fg('#ff4466'))
            footer_layout.addWidget(ttk.TTkLabel(text=right_hint, maxWidth=10))

            main_layout.addWidget(footer_frame)

            # Set initial focus
            if self.panels:
                self.panels[0].setFocus()

            # Run the TUI
            self.root.mainloop()

            return self.result

        except Exception as e:
            # If TUI fails, return None to fall back to classic menu
            import traceback
            traceback.print_exc()
            return None


def run_tui(config: Optional[ServerConfig] = None) -> Optional[tuple]:
    """Run the TUI and return any result."""
    # Show the animated banner first
    show_banner()

    # Then launch the TUI
    app = DarkCodeTUI(config)
    return app.run()
