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
                if len(path_str) > 35:
                    path_str = "..." + path_str[-32:]
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


# Custom banner from file
BANNER_ART = """
         .:::::::--------.                                                        .--------.
         :@@@@@@@+%@@@@@@@#.         .*%%%%%*.#%%%%%%%%%%%%%%%%%%%*@@@@@+       .@@@@@@@@*.
         :@@@@@@@+ .+@@@@@@@#:     -%@@@@@@@#.%@@@@@@@@@@@@@@@@@@@#@@@@@+    .-%@@@@@@@+.
         .-------:    .--------:.-------:----.------.........-----------:  .--------:.
         :@@@@@@@+     .=@@@@@@@@@@@@@:.*@@@#.%@@@@%.*@@@@@@@@@@@@#@@@@@+ =@@@@@@@@:.
         :@@@@@@@+       .#@@@@@@@@*.   *@@@#.%@@@@%.*@@@@@@@@@@@@#@@@@@*%@@@@@@@#.
         :@@@@@@@+     .*@@@@@@@@=......#@@@#.%@@@@%..=%@@@@@*:   =@@@@@+ :%@@@@@@@+.
         :@@@@@@@+   .#@@@@@@@@:.  .*@@@@@@@#.%@@@@%.  ..=@@@@@@+ =@@@@@+  .:%@@@@@@@*.
         :@@@@@@@+ :#@@@@@@@*:       .+*****=.+****+.     .:+*****#@@@@%-     :#@@@@@@@*.
         :@@@@@@@*%@@@@@@@*.                                      =@@+.         .%@@@@@@@#.
         :@@@@@@+::::::::::::..:::::::::::::::::::.::::::::::::::::::...:::::::::::::::::::.
         -@@@#+=============--===================:====================:==================:.
       .-+*==-             .=====:.       .=====:=====.       .:====-======:::::::::::::
      .*%%%%+.            :%%%%%:        -%%%%%=%%%%*.       .*%%%%+#%%%%%%%%%%%%%%%%%#.
     .#@@@@=             :@@@@@:.       =@@@@#*@@@@#.       .#@@@@+@@@@@=
    .%@@@@@@@@@@@@@@@@@@*@@@@@@@@@@@@@@@@@@@#*@@@@@@@@@@@@@@@@@@@-@@@@@@@@@@@@@@@@@@#.
   :#%%%%%%%%%%%%%%%%%#-%%%%%%%%%%%%%%%%%%%=*%%%%%%%%%%%%%%%%*=::%%%%%%%%%%%%%%%%%%+.
"""


class DarkCodeTUI:
    """Main TUI application using pyTermTk."""

    def __init__(self, config: Optional[ServerConfig] = None):
        self.config = config or ServerConfig.load()
        self.system_check = SystemCheck()
        self.result = None
        self.root = None

        # Menu items: (key, title, description, mode/action)
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

    def _get_banner_colored(self) -> str:
        """Get the banner with gradient colors."""
        # Try to load from file first
        banner_paths = [
            Path("/Users/0xdeadbeef/Desktop/tui_banner.txt"),
            Path.home() / ".darkcode" / "tui_banner.txt",
        ]

        banner_text = BANNER_ART
        for path in banner_paths:
            if path.exists():
                try:
                    banner_text = path.read_text()
                    break
                except Exception:
                    pass

        return banner_text.strip()

    def _handle_menu_click(self, text):
        """Handle menu item click."""
        text_str = str(text).strip()

        # Find matching menu item
        for key, title, mode in self._menu_items:
            if title in text_str or text_str in title:
                if key == "quit":
                    self.root.quit()
                elif key.startswith("start_"):
                    self.result = ("start", mode)
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

            # Set up root layout
            root_layout = ttk.TTkGridLayout()
            self.root.setLayout(root_layout)

            # Create main frame
            main_frame = ttk.TTkFrame(border=False)
            main_layout = ttk.TTkVBoxLayout()
            main_frame.setLayout(main_layout)
            root_layout.addWidget(main_frame, 0, 0)

            # === BANNER ===
            banner_text = self._get_banner_colored()
            banner_lines = banner_text.split('\n')

            # Color gradient for banner (magenta -> purple -> blue)
            colors = [
                ttk.TTkColor.fg('#ff00ff'),  # Magenta
                ttk.TTkColor.fg('#ee00ff'),
                ttk.TTkColor.fg('#dd00ff'),
                ttk.TTkColor.fg('#cc00ff'),
                ttk.TTkColor.fg('#bb00ff'),
                ttk.TTkColor.fg('#aa00ff'),
                ttk.TTkColor.fg('#9900ff'),
                ttk.TTkColor.fg('#8800ff'),
                ttk.TTkColor.fg('#7700ff'),
                ttk.TTkColor.fg('#6600ff'),
                ttk.TTkColor.fg('#5500ff'),
                ttk.TTkColor.fg('#4400ff'),
                ttk.TTkColor.fg('#3300ff'),
                ttk.TTkColor.fg('#2200ff'),
                ttk.TTkColor.fg('#1100ff'),
                ttk.TTkColor.fg('#0000ff'),
                ttk.TTkColor.fg('#0011ff'),
            ]

            for i, line in enumerate(banner_lines[:18]):  # Limit banner height
                color = colors[min(i, len(colors) - 1)]
                label = ttk.TTkLabel(text=ttk.TTkString(line, color), maxHeight=1)
                main_layout.addWidget(label)

            # Version label
            version_label = ttk.TTkLabel(
                text=ttk.TTkString(f"  v{__version__}", ttk.TTkColor.fg('#888888')),
                maxHeight=1
            )
            main_layout.addWidget(version_label)

            # Spacer
            main_layout.addWidget(ttk.TTkSpacer())

            # === CONTENT AREA (Status + Menu side by side) ===
            content_layout = ttk.TTkHBoxLayout()
            content_frame = ttk.TTkFrame(border=False, maxHeight=16)
            content_frame.setLayout(content_layout)
            main_layout.addWidget(content_frame)

            # --- System Status Panel ---
            checks = self.system_check.run_all(self.config)

            status_frame = ttk.TTkFrame(title="System Status", border=True, maxWidth=55)
            status_layout = ttk.TTkVBoxLayout()
            status_frame.setLayout(status_layout)

            for name, (ok, msg) in checks.items():
                icon = "✓" if ok else "✗"
                color = ttk.TTkColor.fg('#00ff00') if ok else ttk.TTkColor.fg('#ff4444')
                dim = ttk.TTkColor.fg('#888888')
                text = ttk.TTkString(f" {icon} ", color) + ttk.TTkString(f"{name}: ", ttk.TTkColor.RST) + ttk.TTkString(msg, dim)
                status_layout.addWidget(ttk.TTkLabel(text=text, maxHeight=1))

            status_layout.addWidget(ttk.TTkSpacer())
            content_layout.addWidget(status_frame)

            # Spacer between panels
            content_layout.addWidget(ttk.TTkSpacer())

            # --- Menu Panel ---
            menu_frame = ttk.TTkFrame(title="Menu", border=True, maxWidth=45)
            menu_layout = ttk.TTkVBoxLayout()
            menu_frame.setLayout(menu_layout)

            # Instructions
            hint_text = ttk.TTkString(" ↑↓ Navigate  Enter Select  q Quit", ttk.TTkColor.fg('#666666'))
            menu_layout.addWidget(ttk.TTkLabel(text=hint_text, maxHeight=1))

            # Menu list
            menu_list = ttk.TTkList(minHeight=10)

            for key, title, mode in self._menu_items:
                menu_list.addItem(f"  {title}")

            # Connect signal
            @ttk.pyTTkSlot(str)
            def _menu_clicked(text):
                self._handle_menu_click(text)

            menu_list.textClicked.connect(_menu_clicked)
            menu_layout.addWidget(menu_list)

            content_layout.addWidget(menu_frame)
            content_layout.addWidget(ttk.TTkSpacer())

            # === FOOTER ===
            main_layout.addWidget(ttk.TTkSpacer())
            footer = ttk.TTkLabel(
                text=ttk.TTkString(" DarkCode Server - Remote Claude Code from your phone  |  Press 'q' to quit", ttk.TTkColor.fg('#555555')),
                maxHeight=1
            )
            main_layout.addWidget(footer)

            # Global key handler for quit
            @ttk.pyTTkSlot(ttk.TTkKeyEvent)
            def _global_key_handler(evt):
                if evt.key == ttk.TTkK.Key_Q or evt.key == ttk.TTkK.Key_Escape:
                    self.root.quit()
                    return True
                return False

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
