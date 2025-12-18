"""Simple interactive menu using rich for display."""

import os
import sys
from typing import Optional, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm

console = Console()


def clear_screen():
    """Clear the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')


def show_header():
    """Show the app header."""
    console.print(Panel(
        "[bold magenta]DARKCODE SERVER[/]",
        border_style="magenta",
    ))
    console.print()


def show_main_menu() -> Optional[str]:
    """Show main menu and get selection."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("", style="bold cyan", width=4)
    table.add_column("", style="white")

    options = [
        ("1", "Start Server"),
        ("2", "Server Status"),
        ("3", "Show QR Code"),
        ("4", "Guest Codes"),
        ("5", "Configuration"),
        ("6", "Security Settings"),
        ("7", "Setup Wizard"),
        ("q", "Quit"),
    ]

    for key, label in options:
        table.add_row(f"[{key}]", label)

    console.print(Panel(table, title="[bold]Menu[/]", border_style="cyan"))

    choice = Prompt.ask("\n[cyan]Select[/]", choices=["1", "2", "3", "4", "5", "6", "7", "q"], default="1")

    if choice == "q":
        return None

    actions = {
        "1": "start",
        "2": "status",
        "3": "qr",
        "4": "guest",
        "5": "config",
        "6": "security",
        "7": "setup",
    }
    return actions.get(choice)


def show_connection_menu() -> Optional[str]:
    """Show connection mode selection."""
    from darkcode_server.config import ServerConfig
    config = ServerConfig.load()

    tailscale_ip = config.get_tailscale_ip()

    console.print("\n[bold cyan]Connection Mode[/]\n")

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("", style="bold cyan", width=4)
    table.add_column("", style="white")

    table.add_row("[1]", "Direct LAN - Connect over local network")
    if tailscale_ip:
        table.add_row("[2]", f"Tailscale ({tailscale_ip}) - Secure mesh VPN")
    else:
        table.add_row("[2]", "Tailscale - Not detected")
    table.add_row("[3]", "SSH Tunnel - Localhost only, most secure")
    table.add_row("[b]", "Back")

    console.print(table)

    choice = Prompt.ask("\n[cyan]Select[/]", choices=["1", "2", "3", "b"], default="1")

    if choice == "b":
        return None

    modes = {"1": "direct", "2": "tailscale", "3": "ssh"}
    return modes.get(choice)


def show_guest_menu() -> Optional[str]:
    """Show guest code management menu."""
    console.print("\n[bold green]Guest Access Codes[/]\n")

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("", style="bold cyan", width=4)
    table.add_column("", style="white")

    table.add_row("[1]", "Create New Code")
    table.add_row("[2]", "List All Codes")
    table.add_row("[3]", "Revoke a Code")
    table.add_row("[4]", "Show QR for Code")
    table.add_row("[b]", "Back")

    console.print(table)

    choice = Prompt.ask("\n[cyan]Select[/]", choices=["1", "2", "3", "4", "b"], default="b")

    if choice == "b":
        return None

    actions = {"1": "guest_create", "2": "guest_list", "3": "guest_revoke", "4": "guest_qr"}
    return actions.get(choice)


def show_security_menu() -> Optional[str]:
    """Show security settings menu."""
    from darkcode_server.config import ServerConfig
    config = ServerConfig.load()

    console.print("\n[bold red]Security Settings[/]\n")

    # Current status
    status_table = Table(show_header=False, box=None, padding=(0, 1))
    status_table.add_column("Setting", style="cyan")
    status_table.add_column("Value")

    status_table.add_row("TLS", "[green]enabled[/]" if config.tls_enabled else "[yellow]disabled[/]")
    status_table.add_row("mTLS", "[green]enabled[/]" if config.mtls_enabled else "[dim]disabled[/]")
    status_table.add_row("Device Lock", "[green]enabled[/]" if config.device_lock else "[yellow]disabled[/]")
    status_table.add_row("Bound Device", config.bound_device_id[:12] + "..." if config.bound_device_id else "[dim]none[/]")

    console.print(status_table)
    console.print()

    # Options
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("", style="bold cyan", width=4)
    table.add_column("", style="white")

    table.add_row("[1]", "Toggle TLS")
    table.add_row("[2]", "Toggle mTLS")
    table.add_row("[3]", "Toggle Device Lock")
    table.add_row("[4]", "Reset Auth Token")
    table.add_row("[5]", "View Blocked IPs")
    table.add_row("[6]", "Unbind Device")
    table.add_row("[b]", "Back")

    console.print(table)

    choice = Prompt.ask("\n[cyan]Select[/]", choices=["1", "2", "3", "4", "5", "6", "b"], default="b")

    if choice == "b":
        return None

    actions = {
        "1": "security_tls",
        "2": "security_mtls",
        "3": "security_device_lock",
        "4": "security_reset_token",
        "5": "security_blocked",
        "6": "security_unbind",
    }
    return actions.get(choice)


def execute_action(action: str) -> bool:
    """Execute an action. Returns True to continue, False to exit."""
    from darkcode_server.config import ServerConfig

    if action == "status":
        config = ServerConfig.load()
        console.print("\n[bold cyan]Server Status[/]\n")

        table = Table(show_header=False, box=None)
        table.add_column("Key", style="cyan")
        table.add_column("Value")

        table.add_row("Port", str(config.port))
        table.add_row("Working Dir", str(config.working_dir))
        table.add_row("Server Name", config.server_name)
        table.add_row("TLS", "enabled" if config.tls_enabled else "disabled")
        table.add_row("Device Lock", "enabled" if config.device_lock else "disabled")

        tailscale_ip = config.get_tailscale_ip()
        table.add_row("Tailscale", tailscale_ip if tailscale_ip else "not detected")

        console.print(table)

        # Check daemon
        try:
            from darkcode_server.daemon import DarkCodeDaemon
            pid = DarkCodeDaemon.get_running_pid(config)
            if pid:
                console.print(f"\n[green]Daemon running (PID {pid})[/]")
            else:
                console.print("\n[dim]Daemon not running[/]")
        except:
            pass

        Prompt.ask("\n[dim]Press Enter to continue[/]")
        return True

    elif action == "qr":
        # Actually show the QR code
        from darkcode_server.qrcode import print_server_info
        config = ServerConfig.load()
        console.print()
        print_server_info(config, console)
        Prompt.ask("\n[dim]Press Enter to continue[/]")
        return True

    elif action == "config":
        config = ServerConfig.load()
        console.print("\n[bold cyan]Configuration[/]\n")

        table = Table(show_header=False, box=None)
        table.add_column("Key", style="cyan")
        table.add_column("Value")

        table.add_row("Port", str(config.port))
        table.add_row("Working Dir", str(config.working_dir))
        table.add_row("Server Name", config.server_name)
        table.add_row("Config Dir", str(config.config_dir))
        table.add_row("Token", config.token[:4] + "*" * 16)
        table.add_row("Max Sessions/IP", str(config.max_sessions_per_ip))

        console.print(table)

        if Confirm.ask("\n[cyan]Edit configuration?[/]", default=False):
            new_port = Prompt.ask("Port", default=str(config.port))
            new_dir = Prompt.ask("Working directory", default=str(config.working_dir))
            new_name = Prompt.ask("Server name", default=config.server_name)

            from pathlib import Path
            config.port = int(new_port)
            config.working_dir = Path(new_dir)
            config.server_name = new_name
            config.save()

            console.print("\n[green]Configuration saved![/]")

        Prompt.ask("\n[dim]Press Enter to continue[/]")
        return True

    elif action == "guest_create":
        config = ServerConfig.load()
        from darkcode_server.security import GuestAccessManager

        console.print("\n[bold green]Create Guest Code[/]\n")

        name = Prompt.ask("Friend's name")
        if not name:
            return True

        expires = Prompt.ask("Expires in hours (0=never)", default="24")
        max_uses = Prompt.ask("Max uses (empty=unlimited)", default="")
        read_only = Confirm.ask("Read-only access?", default=False)

        guest_mgr = GuestAccessManager(config.config_dir / "guests.db")
        result = guest_mgr.create_guest_code(
            name=name,
            permission_level="read_only" if read_only else "full",
            expires_hours=int(expires) if expires != "0" else None,
            max_uses=int(max_uses) if max_uses else None,
        )

        console.print(f"\n[green]Created![/] Code: [bold]{result['code']}[/]")
        Prompt.ask("\n[dim]Press Enter to continue[/]")
        return True

    elif action == "guest_list":
        config = ServerConfig.load()
        from darkcode_server.security import GuestAccessManager

        guest_mgr = GuestAccessManager(config.config_dir / "guests.db")
        codes = guest_mgr.list_codes()

        console.print("\n[bold green]Guest Codes[/]\n")

        if not codes:
            console.print("[dim]No guest codes found.[/]")
        else:
            table = Table(show_header=True, box=None)
            table.add_column("Code", style="bold cyan")
            table.add_column("Name")
            table.add_column("Status")

            for code in codes:
                status = "[green]active[/]"
                if not code.get("is_active"):
                    status = "[red]revoked[/]"
                elif code.get("expired"):
                    status = "[yellow]expired[/]"
                table.add_row(code["code"], code["name"], status)

            console.print(table)

        Prompt.ask("\n[dim]Press Enter to continue[/]")
        return True

    elif action == "guest_revoke":
        config = ServerConfig.load()
        from darkcode_server.security import GuestAccessManager

        code = Prompt.ask("[cyan]Code to revoke[/]")
        if not code:
            return True

        guest_mgr = GuestAccessManager(config.config_dir / "guests.db")
        if guest_mgr.revoke_code(code):
            console.print(f"[green]Revoked:[/] {code.upper()}")
        else:
            console.print(f"[red]Not found:[/] {code}")

        Prompt.ask("\n[dim]Press Enter to continue[/]")
        return True

    elif action == "guest_qr":
        from darkcode_server.cli import guest_qr as show_guest_qr
        from click.testing import CliRunner

        code = Prompt.ask("[cyan]Code for QR[/]")
        if not code:
            return True

        runner = CliRunner()
        result = runner.invoke(show_guest_qr, [code], standalone_mode=False)
        if result.output:
            console.print(result.output)

        Prompt.ask("\n[dim]Press Enter to continue[/]")
        return True

    elif action == "security_tls":
        config = ServerConfig.load()
        config.tls_enabled = not config.tls_enabled
        config.save()

        if config.tls_enabled:
            console.print("\n[green]TLS enabled - Server will use wss://[/]")
        else:
            console.print("\n[yellow]TLS disabled - Server will use ws://[/]")

        Prompt.ask("\n[dim]Press Enter to continue[/]")
        return True

    elif action == "security_mtls":
        config = ServerConfig.load()
        config.mtls_enabled = not config.mtls_enabled
        if config.mtls_enabled:
            config.tls_enabled = True
        config.save()

        if config.mtls_enabled:
            console.print("\n[green]mTLS enabled - Clients must present certificates[/]")
        else:
            console.print("\n[dim]mTLS disabled[/]")

        Prompt.ask("\n[dim]Press Enter to continue[/]")
        return True

    elif action == "security_device_lock":
        config = ServerConfig.load()
        config.device_lock = not config.device_lock
        config.save()

        if config.device_lock:
            console.print("\n[green]Device lock enabled[/]")
        else:
            console.print("\n[yellow]Device lock disabled[/]")

        Prompt.ask("\n[dim]Press Enter to continue[/]")
        return True

    elif action == "security_reset_token":
        if Confirm.ask("\n[yellow]Generate new auth token? Current connections will be invalidated.[/]"):
            import secrets
            config = ServerConfig.load()
            config.token = secrets.token_urlsafe(24)
            config.save()

            console.print(f"\n[green]New token:[/] {config.token}")

        Prompt.ask("\n[dim]Press Enter to continue[/]")
        return True

    elif action == "security_blocked":
        config = ServerConfig.load()
        from darkcode_server.security import PersistentRateLimiter

        db_path = config.config_dir / "security.db"
        if not db_path.exists():
            console.print("\n[dim]No security database yet.[/]")
        else:
            rate_limiter = PersistentRateLimiter(db_path)
            blocked = rate_limiter.get_blocked()

            if not blocked:
                console.print("\n[green]No blocked IPs or devices[/]")
            else:
                table = Table(title="Blocked")
                table.add_column("Identifier", style="red")
                table.add_column("Type")

                for b in blocked:
                    table.add_row(b["identifier"][:20], b["identifier_type"])

                console.print(table)

        Prompt.ask("\n[dim]Press Enter to continue[/]")
        return True

    elif action == "security_unbind":
        config = ServerConfig.load()

        if not config.bound_device_id:
            console.print("\n[yellow]No device is currently bound.[/]")
        elif Confirm.ask("\n[yellow]Unbind current device?[/]"):
            config.bound_device_id = None
            config.save()
            console.print("[green]Device unbound.[/]")

        Prompt.ask("\n[dim]Press Enter to continue[/]")
        return True

    return True


def run_interactive_menu() -> Optional[Tuple[str, Optional[str]]]:
    """Run the interactive menu loop.

    Returns:
        Tuple of (action, mode) for actions that need to exit the menu,
        or None if user quit.
    """
    while True:
        clear_screen()
        show_header()

        action = show_main_menu()

        if action is None:
            return None

        if action == "start":
            clear_screen()
            show_header()
            mode = show_connection_menu()
            if mode:
                return ("start", mode)
            continue

        if action == "guest":
            while True:
                clear_screen()
                show_header()
                guest_action = show_guest_menu()
                if guest_action is None:
                    break
                execute_action(guest_action)
            continue

        if action == "security":
            while True:
                clear_screen()
                show_header()
                sec_action = show_security_menu()
                if sec_action is None:
                    break
                execute_action(sec_action)
            continue

        if action == "setup":
            return ("setup", None)

        # Execute other actions inline
        execute_action(action)
