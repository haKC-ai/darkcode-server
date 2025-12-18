"""TUI interface for DarkCode Server using Textual."""

import asyncio
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, ListItem, ListView, Static

from darkcode_server import __version__
from darkcode_server.config import ServerConfig


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
                    return True, f"Claude Code v{version}"
            except Exception:
                pass
        return False, "Not installed - Run: npm install -g @anthropic-ai/claude-code"

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
                    return False, "Installed but not connected - Run: tailscale up"
            except Exception:
                pass
            return False, "Installed but not running"
        return False, "Not installed - https://tailscale.com/download"

    def check_python_version(self) -> tuple[bool, str]:
        """Check Python version."""
        version = sys.version_info
        if version >= (3, 9):
            return True, f"Python {version.major}.{version.minor}.{version.micro}"
        return False, f"Python {version.major}.{version.minor} (need 3.9+)"

    def check_working_dir(self, config: ServerConfig) -> tuple[bool, str]:
        """Check if working directory exists and is accessible."""
        if config.working_dir.exists():
            if config.working_dir.is_dir():
                return True, str(config.working_dir)
            return False, "Path exists but is not a directory"
        return False, f"Directory not found: {config.working_dir}"

    def run_all(self, config: ServerConfig) -> dict:
        """Run all system checks."""
        self.results = {
            "python": self.check_python_version(),
            "claude_code": self.check_claude_code(),
            "tailscale": self.check_tailscale(),
            "working_dir": self.check_working_dir(config),
        }
        return self.results


class StatusWidget(Static):
    """Widget showing system status."""

    def __init__(self, title: str, status: bool, message: str):
        super().__init__()
        self.title = title
        self.status = status
        self.message = message

    def compose(self) -> ComposeResult:
        icon = "✓" if self.status else "✗"
        color = "green" if self.status else "red"
        yield Label(f"[{color}]{icon}[/] [bold]{self.title}[/]: {self.message}")


class MenuOption(ListItem):
    """A menu option item."""

    def __init__(self, key: str, title: str, description: str):
        super().__init__()
        self.key = key
        self.title = title
        self.description = description

    def compose(self) -> ComposeResult:
        yield Label(f"[bold cyan]{self.title}[/]")
        yield Label(f"[dim]{self.description}[/]")


class MainMenu(Screen):
    """Main menu screen with arrow key navigation."""

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("enter", "select", "Select"),
        Binding("1", "option_1", "Start Server"),
        Binding("2", "option_2", "Status"),
        Binding("3", "option_3", "QR Code"),
        Binding("4", "option_4", "Guest Codes"),
        Binding("5", "option_5", "Config"),
        Binding("6", "option_6", "Security"),
        Binding("7", "option_7", "Setup"),
    ]

    def __init__(self, config: ServerConfig, system_check: SystemCheck):
        super().__init__()
        self.config = config
        self.system_check = system_check

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Container(id="main"):
            # Banner
            yield Static(
                "[bold magenta]DARKCODE[/] [dim]Server[/]",
                id="banner"
            )
            yield Static(f"[dim]v{__version__}[/]", id="version")

            # System status
            with Container(id="status-panel"):
                yield Static("[bold]System Status[/]", id="status-title")
                checks = self.system_check.results
                for name, (ok, msg) in checks.items():
                    icon = "[green]✓[/]" if ok else "[red]✗[/]"
                    label = name.replace("_", " ").title()
                    yield Static(f"{icon} {label}: [dim]{msg}[/]")

            # Menu
            with Container(id="menu-panel"):
                yield Static("[bold]Menu[/] [dim](use ↑↓ arrows or number keys)[/]", id="menu-title")
                yield ListView(
                    MenuOption("start", "Start Server", "Launch the WebSocket server"),
                    MenuOption("status", "Server Status", "Check if server is running"),
                    MenuOption("qr", "Show QR Code", "Display connection QR code"),
                    MenuOption("guest", "Guest Codes", "Create/manage friend access codes"),
                    MenuOption("config", "Configuration", "View/edit server settings"),
                    MenuOption("security", "Security", "TLS, tokens, blocked IPs"),
                    MenuOption("setup", "Setup Wizard", "Re-run initial setup"),
                    id="menu-list"
                )

        yield Footer()

    def action_quit(self):
        self.app.exit()

    def action_select(self):
        menu = self.query_one("#menu-list", ListView)
        if menu.highlighted_child:
            item = menu.highlighted_child
            if isinstance(item, MenuOption):
                self.handle_option(item.key)

    def action_option_1(self):
        self.handle_option("start")

    def action_option_2(self):
        self.handle_option("status")

    def action_option_3(self):
        self.handle_option("qr")

    def action_option_4(self):
        self.handle_option("guest")

    def action_option_5(self):
        self.handle_option("config")

    def action_option_6(self):
        self.handle_option("security")

    def action_option_7(self):
        self.handle_option("setup")

    def handle_option(self, key: str):
        """Handle menu option selection."""
        if key == "start":
            self.app.push_screen(StartServerScreen(self.config))
        elif key == "status":
            self.app.push_screen(StatusScreen(self.config))
        elif key == "qr":
            self.app.push_screen(QRScreen(self.config))
        elif key == "guest":
            self.app.push_screen(GuestScreen(self.config))
        elif key == "config":
            self.app.push_screen(ConfigScreen(self.config))
        elif key == "security":
            self.app.push_screen(SecurityScreen(self.config))
        elif key == "setup":
            self.app.push_screen(SetupScreen(self.config))

    @on(ListView.Selected)
    def on_list_selected(self, event: ListView.Selected):
        if isinstance(event.item, MenuOption):
            self.handle_option(event.item.key)


class StartServerScreen(Screen):
    """Screen for starting the server."""

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("q", "back", "Back"),
    ]

    def __init__(self, config: ServerConfig):
        super().__init__()
        self.config = config

    def compose(self) -> ComposeResult:
        yield Header()
        with Container():
            yield Static("[bold cyan]Start Server[/]", id="title")
            yield Static("")
            yield Static("[bold]Connection Mode[/]")
            yield ListView(
                MenuOption("direct", "Direct LAN", "Connect over local network"),
                MenuOption("tailscale", "Tailscale", "Secure mesh VPN"),
                MenuOption("ssh", "SSH Tunnel", "Localhost only, most secure"),
                id="mode-list"
            )
        yield Footer()

    def action_back(self):
        self.app.pop_screen()

    @on(ListView.Selected)
    def on_mode_selected(self, event: ListView.Selected):
        if isinstance(event.item, MenuOption):
            # Exit TUI and start server with selected mode
            mode = event.item.key
            self.app.exit(result=("start", mode))


class StatusScreen(Screen):
    """Screen showing server status."""

    BINDINGS = [Binding("escape", "back", "Back")]

    def __init__(self, config: ServerConfig):
        super().__init__()
        self.config = config

    def compose(self) -> ComposeResult:
        yield Header()
        with Container():
            yield Static("[bold cyan]Server Status[/]", id="title")
            yield Static("")
            yield Static(f"[cyan]Port:[/] {self.config.port}")
            yield Static(f"[cyan]Working Dir:[/] {self.config.working_dir}")
            yield Static(f"[cyan]Config Dir:[/] {self.config.config_dir}")
            yield Static("")
            # TODO: Check if daemon is running
            yield Static("[yellow]Status check not yet implemented[/]")
        yield Footer()

    def action_back(self):
        self.app.pop_screen()


class QRScreen(Screen):
    """Screen showing QR codes."""

    BINDINGS = [Binding("escape", "back", "Back")]

    def __init__(self, config: ServerConfig):
        super().__init__()
        self.config = config

    def compose(self) -> ComposeResult:
        yield Header()
        with Container():
            yield Static("[bold cyan]Connection QR Code[/]", id="title")
            yield Static("")
            yield Static("[dim]Generating QR code...[/]")
            # TODO: Generate and display QR code
        yield Footer()

    def action_back(self):
        self.app.pop_screen()


class GuestScreen(Screen):
    """Screen for managing guest codes."""

    BINDINGS = [Binding("escape", "back", "Back")]

    def __init__(self, config: ServerConfig):
        super().__init__()
        self.config = config

    def compose(self) -> ComposeResult:
        yield Header()
        with Container():
            yield Static("[bold cyan]Guest Access Codes[/]", id="title")
            yield Static("")
            yield ListView(
                MenuOption("create", "Create New Code", "Generate a new guest code"),
                MenuOption("list", "List Codes", "View all guest codes"),
                MenuOption("revoke", "Revoke Code", "Disable a guest code"),
                id="guest-menu"
            )
        yield Footer()

    def action_back(self):
        self.app.pop_screen()


class ConfigScreen(Screen):
    """Screen for configuration."""

    BINDINGS = [Binding("escape", "back", "Back")]

    def __init__(self, config: ServerConfig):
        super().__init__()
        self.config = config

    def compose(self) -> ComposeResult:
        yield Header()
        with Container():
            yield Static("[bold cyan]Configuration[/]", id="title")
            yield Static("")
            yield Static(f"[cyan]Port:[/] {self.config.port}")
            yield Static(f"[cyan]Working Dir:[/] {self.config.working_dir}")
            yield Static(f"[cyan]Server Name:[/] {self.config.server_name}")
            yield Static(f"[cyan]Token:[/] {self.config.token[:4]}{'*' * 16}")
            yield Static(f"[cyan]Max Sessions/IP:[/] {self.config.max_sessions_per_ip}")
        yield Footer()

    def action_back(self):
        self.app.pop_screen()


class SecurityScreen(Screen):
    """Screen for security settings."""

    BINDINGS = [Binding("escape", "back", "Back")]

    def __init__(self, config: ServerConfig):
        super().__init__()
        self.config = config

    def compose(self) -> ComposeResult:
        yield Header()
        with Container():
            yield Static("[bold cyan]Security Settings[/]", id="title")
            yield Static("")

            tls_status = "[green]enabled[/]" if self.config.tls_enabled else "[yellow]disabled[/]"
            mtls_status = "[green]enabled[/]" if self.config.mtls_enabled else "[dim]disabled[/]"
            device_lock = "[green]enabled[/]" if self.config.device_lock else "[yellow]disabled[/]"

            yield Static(f"[cyan]TLS:[/] {tls_status}")
            yield Static(f"[cyan]mTLS:[/] {mtls_status}")
            yield Static(f"[cyan]Device Lock:[/] {device_lock}")
            yield Static(f"[cyan]Local Only:[/] {'[green]yes[/]' if self.config.local_only else '[yellow]no[/]'}")
        yield Footer()

    def action_back(self):
        self.app.pop_screen()


class SetupScreen(Screen):
    """Setup wizard screen."""

    BINDINGS = [Binding("escape", "back", "Back")]

    def __init__(self, config: ServerConfig):
        super().__init__()
        self.config = config

    def compose(self) -> ComposeResult:
        yield Header()
        with Container():
            yield Static("[bold cyan]Setup Wizard[/]", id="title")
            yield Static("")
            yield Static("[dim]Setup wizard coming soon...[/]")
            yield Static("")
            yield Static("For now, use: [bold]darkcode setup[/]")
        yield Footer()

    def action_back(self):
        self.app.pop_screen()


class DarkCodeTUI(App):
    """Main TUI application."""

    CSS = """
    #main {
        padding: 1;
    }

    #banner {
        text-align: center;
        padding: 1;
    }

    #version {
        text-align: center;
        margin-bottom: 1;
    }

    #status-panel {
        border: solid $primary;
        padding: 1;
        margin-bottom: 1;
    }

    #status-title {
        margin-bottom: 1;
    }

    #menu-panel {
        border: solid $secondary;
        padding: 1;
    }

    #menu-title {
        margin-bottom: 1;
    }

    #menu-list {
        height: auto;
    }

    MenuOption {
        padding: 1;
    }

    MenuOption:hover {
        background: $boost;
    }

    ListView > ListItem.--highlight {
        background: $accent;
    }

    #title {
        text-align: center;
        padding: 1;
        margin-bottom: 1;
    }
    """

    TITLE = "DarkCode Server"
    SUB_TITLE = f"v{__version__}"

    def __init__(self, config: Optional[ServerConfig] = None):
        super().__init__()
        self.config = config or ServerConfig.load()
        self.system_check = SystemCheck()

    def on_mount(self):
        # Run system checks
        self.system_check.run_all(self.config)
        # Show main menu
        self.push_screen(MainMenu(self.config, self.system_check))


def run_tui(config: Optional[ServerConfig] = None) -> Optional[tuple]:
    """Run the TUI and return any result."""
    app = DarkCodeTUI(config)
    return app.run()
