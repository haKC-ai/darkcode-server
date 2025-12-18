"""TUI interface for DarkCode Server using pyTermTk."""

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

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
            Path.home() / ".darkcode" / "banner.txt",
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
                return True, str(config.working_dir)[:30] + "..."
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


class DarkCodeTUI:
    """Main TUI application using pyTermTk."""

    # ASCII art banner
    BANNER = """
██████╗  █████╗ ██████╗ ██╗  ██╗ ██████╗ ██████╗ ██████╗ ███████╗
██╔══██╗██╔══██╗██╔══██╗██║ ██╔╝██╔════╝██╔═══██╗██╔══██╗██╔════╝
██║  ██║███████║██████╔╝█████╔╝ ██║     ██║   ██║██║  ██║█████╗
██║  ██║██╔══██║██╔══██╗██╔═██╗ ██║     ██║   ██║██║  ██║██╔══╝
██████╔╝██║  ██║██║  ██║██║  ██╗╚██████╗╚██████╔╝██████╔╝███████╗
╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝
"""

    def __init__(self, config: Optional[ServerConfig] = None):
        self.config = config or ServerConfig.load()
        self.system_check = SystemCheck()
        self.result = None
        self.root = None
        self._selected_index = 0
        self._menu_items = []

    def _get_banner_colored(self) -> ttk.TTkString:
        """Get the banner with gradient colors."""
        lines = self.BANNER.strip().split('\n')
        colored_lines = []

        # Purple to cyan gradient
        colors = [
            ttk.TTkColor.fg('#ff00ff'),  # Magenta
            ttk.TTkColor.fg('#dd00ff'),
            ttk.TTkColor.fg('#bb00ff'),
            ttk.TTkColor.fg('#9900ff'),  # Purple
            ttk.TTkColor.fg('#7700ff'),
            ttk.TTkColor.fg('#5500ff'),
        ]

        for i, line in enumerate(lines):
            color = colors[min(i, len(colors) - 1)]
            colored_lines.append(ttk.TTkString(line, color))

        return ttk.TTkString('\n').join(colored_lines)

    def _create_status_frame(self) -> ttk.TTkFrame:
        """Create the system status frame."""
        checks = self.system_check.run_all(self.config)

        frame = ttk.TTkFrame(
            title=" System Status ",
            border=True,
            size=(50, len(checks) + 2)
        )

        layout = ttk.TTkVBoxLayout()
        frame.setLayout(layout)

        for name, (ok, msg) in checks.items():
            icon = "✓" if ok else "✗"
            color = ttk.TTkColor.fg('#00ff00') if ok else ttk.TTkColor.fg('#ff0000')
            text = ttk.TTkString(f" {icon} ", color) + ttk.TTkString(f"{name}: ") + ttk.TTkString(msg, ttk.TTkColor.fg('#888888'))
            label = ttk.TTkLabel(text=text)
            layout.addWidget(label)

        return frame

    def _create_menu_frame(self) -> ttk.TTkFrame:
        """Create the main menu frame with selectable items."""
        self._menu_items = [
            ("start", "Start Server", "Launch the WebSocket server", "direct"),
            ("start_ts", "Start (Tailscale)", "Start with Tailscale mode", "tailscale"),
            ("start_ssh", "Start (SSH Tunnel)", "Localhost only, most secure", "ssh"),
            ("status", "Server Status", "Check if server is running", None),
            ("qr", "Show QR Code", "Display connection QR code", None),
            ("guest", "Guest Codes", "Create/manage friend access codes", None),
            ("config", "Configuration", "View/edit server settings", None),
            ("security", "Security", "TLS, tokens, blocked IPs", None),
            ("setup", "Setup Wizard", "Re-run initial setup", None),
            ("quit", "Quit", "Exit the application", None),
        ]

        frame = ttk.TTkFrame(
            title=" Menu ",
            border=True,
            size=(50, len(self._menu_items) + 3)
        )

        layout = ttk.TTkVBoxLayout()
        frame.setLayout(layout)

        # Instructions
        hint = ttk.TTkLabel(text=ttk.TTkString(" ↑↓ Navigate  Enter Select  q Quit", ttk.TTkColor.fg('#666666')))
        layout.addWidget(hint)

        # Menu list widget
        self._list_widget = ttk.TTkList(size=(48, len(self._menu_items)))

        for key, title, desc, _ in self._menu_items:
            text = f"  {title}"
            self._list_widget.addItem(ttk.TTkString(text))

        # Select first item
        self._list_widget.setCurrentRow(0)

        # Connect selection signal
        self._list_widget.itemClicked.connect(self._on_item_clicked)

        layout.addWidget(self._list_widget)

        return frame

    def _on_item_clicked(self, item):
        """Handle menu item selection."""
        idx = self._list_widget.currentRow()
        if 0 <= idx < len(self._menu_items):
            key, _, _, mode = self._menu_items[idx]
            self._handle_selection(key, mode)

    def _handle_selection(self, key: str, mode: Optional[str]):
        """Handle a menu selection."""
        if key == "quit":
            self.root.quit()
        elif key.startswith("start"):
            self.result = ("start", mode or "direct")
            self.root.quit()
        elif key == "status":
            self.result = ("status", None)
            self.root.quit()
        elif key == "qr":
            self.result = ("qr", None)
            self.root.quit()
        elif key == "guest":
            self.result = ("guest", None)
            self.root.quit()
        elif key == "config":
            self.result = ("config", None)
            self.root.quit()
        elif key == "security":
            self.result = ("security", None)
            self.root.quit()
        elif key == "setup":
            self.result = ("setup", None)
            self.root.quit()

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

            # Create main layout
            main_layout = ttk.TTkGridLayout()
            self.root.setLayout(main_layout)

            # Create a main window/frame
            main_frame = ttk.TTkFrame(border=False)
            main_frame_layout = ttk.TTkVBoxLayout()
            main_frame.setLayout(main_frame_layout)

            # Banner
            banner_label = ttk.TTkLabel(text=self._get_banner_colored())
            main_frame_layout.addWidget(banner_label)

            # Version
            version_text = ttk.TTkString(f"                           v{__version__}", ttk.TTkColor.fg('#666666'))
            version_label = ttk.TTkLabel(text=version_text)
            main_frame_layout.addWidget(version_label)

            # Spacer
            main_frame_layout.addWidget(ttk.TTkSpacer())

            # Horizontal layout for status and menu
            h_layout = ttk.TTkHBoxLayout()

            # Status frame
            status_frame = self._create_status_frame()
            h_layout.addWidget(status_frame)

            # Spacer between
            h_layout.addWidget(ttk.TTkSpacer())

            # Menu frame
            menu_frame = self._create_menu_frame()
            h_layout.addWidget(menu_frame)

            h_layout.addWidget(ttk.TTkSpacer())

            container = ttk.TTkFrame(border=False)
            container.setLayout(h_layout)
            main_frame_layout.addWidget(container)

            # Footer
            main_frame_layout.addWidget(ttk.TTkSpacer())
            footer = ttk.TTkLabel(text=ttk.TTkString(" DarkCode Server - Remote Claude Code from your phone ", ttk.TTkColor.fg('#555555')))
            main_frame_layout.addWidget(footer)

            main_layout.addWidget(main_frame, 0, 0)

            # Handle keyboard shortcuts
            @ttk.pyTTkSlot(ttk.TTkKeyEvent)
            def _key_handler(evt):
                if evt.key == ttk.TTkK.Key_Q or evt.key == ttk.TTkK.Key_Escape:
                    self.root.quit()
                elif evt.key == ttk.TTkK.Key_Enter or evt.key == ttk.TTkK.Key_Return:
                    idx = self._list_widget.currentRow()
                    if 0 <= idx < len(self._menu_items):
                        key, _, _, mode = self._menu_items[idx]
                        self._handle_selection(key, mode)

            self.root.keyEvent = _key_handler

            # Run the application
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
