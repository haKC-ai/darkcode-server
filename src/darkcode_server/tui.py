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


class DarkCodeTUI:
    """Main TUI application using pyTermTk."""

    def __init__(self, config: Optional[ServerConfig] = None):
        self.config = config or ServerConfig.load()
        self.system_check = SystemCheck()
        self.result = None
        self.root = None
        self.menu_list = None
        self.selected_index = 0

        # Menu items: (key, title, mode/action)
        self._menu_items = [
            ("start_direct", "Start Server (Direct LAN)", "direct"),
            ("start_tailscale", "Start Server (Tailscale)", "tailscale"),
            ("start_ssh", "Start Server (SSH Tunnel)", "ssh"),
            ("status", "Server Status", None),
            ("qr", "Show QR Code", None),
            ("guest", "Guest Codes", None),
            ("config", "Configuration", None),
            ("security", "Security Settings", None),
            ("setup", "Setup Wizard", None),
            ("quit", "Quit", None),
        ]

    def _get_banner_text(self) -> str:
        """Get the banner text."""
        # Try to load from file first
        banner_paths = [
            Path("/Users/0xdeadbeef/Desktop/tui_banner.txt"),
            Path.home() / ".darkcode" / "tui_banner.txt",
        ]

        for path in banner_paths:
            if path.exists():
                try:
                    return path.read_text().strip()
                except Exception:
                    pass

        return BANNER_COMPACT.strip()

    def _select_menu_item(self, index: int):
        """Execute the selected menu item."""
        if 0 <= index < len(self._menu_items):
            key, title, mode = self._menu_items[index]

            if key == "quit":
                self.root.quit()
            elif key.startswith("start_"):
                self.result = ("start", mode)
                self.root.quit()
            else:
                self.result = (key, None)
                self.root.quit()

    def _handle_menu_click(self, text):
        """Handle menu item click."""
        text_str = str(text).strip()

        # Find matching menu item
        for i, (key, title, mode) in enumerate(self._menu_items):
            if title in text_str or text_str in title:
                self._select_menu_item(i)
                break

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

            # Main vertical layout
            main_layout = ttk.TTkVBoxLayout()
            self.root.setLayout(main_layout)

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
            banner_frame = ttk.TTkFrame(border=False, maxHeight=len(banner_lines) + 2)
            banner_layout = ttk.TTkVBoxLayout()
            banner_frame.setLayout(banner_layout)

            for i, line in enumerate(banner_lines[:20]):
                color_hex = gradient[min(i, len(gradient) - 1)]
                color = ttk.TTkColor.fg(color_hex)
                label = ttk.TTkLabel(text=ttk.TTkString(line, color), maxHeight=1)
                banner_layout.addWidget(label)

            main_layout.addWidget(banner_frame)

            # Version & subtitle
            version_text = ttk.TTkString(
                f"  v{__version__} - Remote Claude Code from your phone",
                ttk.TTkColor.fg('#888888')
            )
            main_layout.addWidget(ttk.TTkLabel(text=version_text, maxHeight=1))

            # Separator
            main_layout.addWidget(ttk.TTkLabel(
                text=ttk.TTkString("─" * 80, ttk.TTkColor.fg('#444444')),
                maxHeight=1
            ))

            # === MAIN CONTENT: Side-by-side panels ===
            content_frame = ttk.TTkFrame(border=False)
            content_layout = ttk.TTkHBoxLayout()
            content_frame.setLayout(content_layout)

            # --- LEFT: System Status ---
            status_frame = ttk.TTkFrame(
                title=" System Status ",
                border=True,
                minWidth=40,
                maxWidth=50
            )
            status_layout = ttk.TTkVBoxLayout()
            status_frame.setLayout(status_layout)

            # Add spacer at top
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
                for ip_info in ips[:3]:  # Show up to 3 interfaces
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
            content_layout.addWidget(status_frame)

            # --- RIGHT: Menu ---
            menu_frame = ttk.TTkFrame(
                title=" Menu ",
                border=True,
                minWidth=40
            )
            menu_layout = ttk.TTkVBoxLayout()
            menu_frame.setLayout(menu_layout)

            # Instructions
            hint = ttk.TTkString(
                "  ↑↓ Navigate │ Enter Select │ q Quit",
                ttk.TTkColor.fg('#666666')
            )
            menu_layout.addWidget(ttk.TTkLabel(text=hint, maxHeight=1))
            menu_layout.addWidget(ttk.TTkLabel(text="", maxHeight=1))

            # Menu list widget
            self.menu_list = ttk.TTkList(minHeight=12)

            # Add menu items with nice formatting
            for i, (key, title, mode) in enumerate(self._menu_items):
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
                    icon = "🔒"
                elif key == "config":
                    icon = "⚙"
                elif key == "setup":
                    icon = "★"
                else:
                    icon = "›"

                self.menu_list.addItem(f"  {icon}  {title}")

            # Connect click signal
            @ttk.pyTTkSlot(str)
            def _on_menu_click(text):
                text_str = str(text).strip()
                if text_str.startswith("─"):
                    return  # Ignore separator clicks
                self._handle_menu_click(text)

            self.menu_list.textClicked.connect(_on_menu_click)
            menu_layout.addWidget(self.menu_list)

            content_layout.addWidget(menu_frame)
            main_layout.addWidget(content_frame)

            # === FOOTER ===
            footer_text = ttk.TTkString(
                " Press 'q' to quit │ Tab to switch panels │ Enter to select",
                ttk.TTkColor.fg('#555555')
            )
            main_layout.addWidget(ttk.TTkLabel(text=footer_text, maxHeight=1))

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
