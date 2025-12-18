"""Interactive menu using simple-term-menu for arrow key navigation."""

import os
import sys
from typing import Optional, Tuple

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.prompt import Prompt, Confirm
from simple_term_menu import TerminalMenu

console = Console()


def clear_screen():
    """Clear the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')


def show_header():
    """Show minimal app header."""
    console.print()
    console.print("[bold magenta]DARKCODE SERVER[/]", justify="center")
    console.print("[dim]Remote Claude Code Control[/]", justify="center")
    console.print()


def fancy_progress(description: str, steps: int = 10):
    """Show a fancy progress animation."""
    import time
    with Progress(
        SpinnerColumn("dots"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=20),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task(description, total=steps)
        for _ in range(steps):
            time.sleep(0.05)
            progress.advance(task)


def show_menu(title: str, options: list, back_option: bool = False) -> Optional[str]:
    """Show a menu with arrow key navigation.

    Args:
        title: Menu title
        options: List of (key, value, description) tuples
        back_option: Whether to show a back option

    Returns:
        Selected value or None if back/quit/escape
    """
    console.print(f"\n[bold cyan]{title}[/]\n")

    # Build menu entries
    entries = [f"[{key}] {desc}" for key, value, desc in options]
    if back_option:
        entries.append("[b] Back")

    # Create terminal menu with styling
    menu = TerminalMenu(
        entries,
        menu_cursor="▸ ",
        menu_cursor_style=("fg_cyan", "bold"),
        menu_highlight_style=("fg_green", "bold"),
        cycle_cursor=True,
        clear_screen=False,
    )

    idx = menu.show()

    if idx is None:
        return None

    if back_option and idx == len(options):
        return None

    return options[idx][1] if idx < len(options) else None


def show_main_menu() -> Optional[str]:
    """Show main menu and get selection."""
    options = [
        ("1", "start", "Start Server"),
        ("2", "status", "Server Status"),
        ("3", "qr", "Show QR Code"),
        ("4", "guest", "Guest Codes"),
        ("5", "config", "Configuration"),
        ("6", "security", "Security Settings"),
        ("7", "setup", "Setup Wizard"),
        ("q", "quit", "Quit"),
    ]

    result = show_menu("Main Menu", options)
    return None if result == "quit" else result


def show_connection_menu() -> Optional[str]:
    """Show connection mode selection."""
    from darkcode_server.config import ServerConfig
    config = ServerConfig.load()

    tailscale_ip = config.get_tailscale_ip()

    options = [
        ("1", "direct", "Direct LAN - Local network connection"),
    ]

    if tailscale_ip:
        options.append(("2", "tailscale", f"Tailscale ({tailscale_ip}) - Secure mesh VPN"))
    else:
        options.append(("2", "tailscale_disabled", "Tailscale - Not detected"))

    options.append(("3", "ssh", "SSH Tunnel - Localhost only, most secure"))

    result = show_menu("Connection Mode", options, back_option=True)

    if result == "tailscale_disabled":
        console.print("\n[yellow]Tailscale not detected. Install from tailscale.com[/]")
        Prompt.ask("\n[dim]Press Enter to continue[/]")
        return None

    return result


def show_guest_menu() -> Optional[str]:
    """Show guest code management menu."""
    options = [
        ("1", "guest_create", "Create New Code"),
        ("2", "guest_list", "List All Codes"),
        ("3", "guest_revoke", "Revoke a Code"),
        ("4", "guest_qr", "Show QR for Code"),
    ]

    return show_menu("Guest Access", options, back_option=True)


def show_security_menu() -> Optional[str]:
    """Show security settings menu."""
    from darkcode_server.config import ServerConfig
    config = ServerConfig.load()

    # Show current status first
    console.print()
    console.print("[bold]Current Security Status[/]")
    tls = "[green]ON[/]" if config.tls_enabled else "[yellow]OFF[/]"
    mtls = "[green]ON[/]" if config.mtls_enabled else "[dim]OFF[/]"
    device_lock = "[green]ON[/]" if config.device_lock else "[yellow]OFF[/]"
    bound = config.bound_device_id[:12] + "..." if config.bound_device_id else "[dim]none[/]"

    console.print(f"  TLS: {tls}  |  mTLS: {mtls}  |  Device Lock: {device_lock}")
    console.print(f"  Bound Device: {bound}")

    options = [
        ("1", "security_tls", f"Toggle TLS (currently {'ON' if config.tls_enabled else 'OFF'})"),
        ("2", "security_mtls", f"Toggle mTLS (currently {'ON' if config.mtls_enabled else 'OFF'})"),
        ("3", "security_device_lock", f"Toggle Device Lock (currently {'ON' if config.device_lock else 'OFF'})"),
        ("4", "security_reset_token", "Reset Auth Token"),
        ("5", "security_blocked", "View Blocked IPs"),
        ("6", "security_unbind", "Unbind Device"),
    ]

    return show_menu("Security Settings", options, back_option=True)


def execute_action(action: str) -> bool:
    """Execute an action. Returns True to continue, False to exit."""
    from darkcode_server.config import ServerConfig

    if action == "status":
        config = ServerConfig.load()
        fancy_progress("Loading status...", 5)

        console.print()
        console.print("[bold cyan]Server Status[/]")
        console.print()
        console.print(f"  Port:        [white]{config.port}[/]")
        console.print(f"  Working Dir: [white]{config.working_dir}[/]")
        console.print(f"  Server Name: [white]{config.server_name}[/]")
        console.print(f"  TLS:         {'[green]enabled[/]' if config.tls_enabled else '[yellow]disabled[/]'}")
        console.print(f"  Device Lock: {'[green]enabled[/]' if config.device_lock else '[yellow]disabled[/]'}")

        tailscale_ip = config.get_tailscale_ip()
        console.print(f"  Tailscale:   {tailscale_ip if tailscale_ip else '[dim]not detected[/]'}")

        # Check daemon
        try:
            from darkcode_server.daemon import DarkCodeDaemon
            pid = DarkCodeDaemon.get_running_pid(config)
            if pid:
                console.print(f"\n  [green]Daemon running (PID {pid})[/]")
            else:
                console.print("\n  [dim]Daemon not running[/]")
        except:
            pass

        console.print()
        Prompt.ask("[dim]Press Enter to continue[/]")
        return True

    elif action == "qr":
        fancy_progress("Generating QR code...", 8)
        from darkcode_server.qrcode import print_server_info
        config = ServerConfig.load()
        console.print()
        print_server_info(config, console)
        console.print()
        Prompt.ask("[dim]Press Enter to continue[/]")
        return True

    elif action == "config":
        config = ServerConfig.load()

        console.print()
        console.print("[bold cyan]Current Configuration[/]")
        console.print()
        console.print(f"  Port:            [white]{config.port}[/]")
        console.print(f"  Working Dir:     [white]{config.working_dir}[/]")
        console.print(f"  Server Name:     [white]{config.server_name}[/]")
        console.print(f"  Config Dir:      [white]{config.config_dir}[/]")
        console.print(f"  Token:           [white]{config.token[:4]}{'*' * 16}[/]")
        console.print(f"  Max Sessions/IP: [white]{config.max_sessions_per_ip}[/]")
        console.print()

        if Confirm.ask("Edit configuration?", default=False):
            new_port = Prompt.ask("Port", default=str(config.port))
            new_dir = Prompt.ask("Working directory", default=str(config.working_dir))
            new_name = Prompt.ask("Server name", default=config.server_name)

            if new_port and new_dir and new_name:
                from pathlib import Path
                config.port = int(new_port)
                config.working_dir = Path(new_dir)
                config.server_name = new_name
                config.save()

                fancy_progress("Saving configuration...", 5)
                console.print("\n[green]Configuration saved![/]")

        Prompt.ask("[dim]Press Enter to continue[/]")
        return True

    elif action == "guest_create":
        console.print()
        console.print("[bold green]Create Guest Code[/]")
        console.print()

        name = Prompt.ask("Friend's name")
        if not name:
            return True

        expires = Prompt.ask("Expires in hours (0=never)", default="24")
        max_uses = Prompt.ask("Max uses (empty=unlimited)", default="")
        read_only = Confirm.ask("Read-only access?", default=False)

        fancy_progress("Creating guest code...", 8)

        config = ServerConfig.load()
        from darkcode_server.security import GuestAccessManager

        guest_mgr = GuestAccessManager(config.config_dir / "guests.db")
        result = guest_mgr.create_guest_code(
            name=name,
            permission_level="read_only" if read_only else "full",
            expires_hours=int(expires) if expires != "0" else None,
            max_uses=int(max_uses) if max_uses else None,
        )

        console.print(f"\n[green]Created![/] Code: [bold white]{result['code']}[/]")
        Prompt.ask("[dim]Press Enter to continue[/]")
        return True

    elif action == "guest_list":
        config = ServerConfig.load()
        from darkcode_server.security import GuestAccessManager

        fancy_progress("Loading guest codes...", 5)

        guest_mgr = GuestAccessManager(config.config_dir / "guests.db")
        codes = guest_mgr.list_codes()

        console.print()
        console.print("[bold green]Guest Codes[/]")
        console.print()

        if not codes:
            console.print("[dim]No guest codes found.[/]")
        else:
            for code in codes:
                status = "[green]active[/]"
                if not code.get("is_active"):
                    status = "[red]revoked[/]"
                elif code.get("expired"):
                    status = "[yellow]expired[/]"
                console.print(f"  [bold cyan]{code['code']}[/] - {code['name']} ({status})")

        console.print()
        Prompt.ask("[dim]Press Enter to continue[/]")
        return True

    elif action == "guest_revoke":
        code = Prompt.ask("[cyan]Code to revoke[/]")
        if not code:
            return True

        config = ServerConfig.load()
        from darkcode_server.security import GuestAccessManager

        fancy_progress("Revoking code...", 5)

        guest_mgr = GuestAccessManager(config.config_dir / "guests.db")
        if guest_mgr.revoke_code(code):
            console.print(f"\n[green]Revoked:[/] {code.upper()}")
        else:
            console.print(f"\n[red]Not found:[/] {code}")

        Prompt.ask("[dim]Press Enter to continue[/]")
        return True

    elif action == "guest_qr":
        code = Prompt.ask("[cyan]Code for QR[/]")
        if not code:
            return True

        fancy_progress("Generating QR code...", 8)

        from darkcode_server.cli import guest_qr as show_guest_qr
        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(show_guest_qr, [code], standalone_mode=False)
        if result.output:
            console.print(result.output)

        Prompt.ask("[dim]Press Enter to continue[/]")
        return True

    elif action == "security_tls":
        config = ServerConfig.load()
        config.tls_enabled = not config.tls_enabled
        config.save()

        fancy_progress("Updating TLS setting...", 5)

        if config.tls_enabled:
            console.print("\n[green]TLS enabled - Server will use wss://[/]")
        else:
            console.print("\n[yellow]TLS disabled - Server will use ws://[/]")

        Prompt.ask("[dim]Press Enter to continue[/]")
        return True

    elif action == "security_mtls":
        config = ServerConfig.load()
        config.mtls_enabled = not config.mtls_enabled
        if config.mtls_enabled:
            config.tls_enabled = True
        config.save()

        fancy_progress("Updating mTLS setting...", 5)

        if config.mtls_enabled:
            console.print("\n[green]mTLS enabled - Clients must present certificates[/]")
        else:
            console.print("\n[dim]mTLS disabled[/]")

        Prompt.ask("[dim]Press Enter to continue[/]")
        return True

    elif action == "security_device_lock":
        config = ServerConfig.load()
        config.device_lock = not config.device_lock
        config.save()

        fancy_progress("Updating device lock...", 5)

        if config.device_lock:
            console.print("\n[green]Device lock enabled[/]")
        else:
            console.print("\n[yellow]Device lock disabled[/]")

        Prompt.ask("[dim]Press Enter to continue[/]")
        return True

    elif action == "security_reset_token":
        if Confirm.ask("Generate new auth token? Current connections will be invalidated.", default=False):
            import secrets
            config = ServerConfig.load()
            config.token = secrets.token_urlsafe(24)
            config.save()

            fancy_progress("Generating new token...", 8)
            console.print(f"\n[green]New token:[/] {config.token}")

        Prompt.ask("[dim]Press Enter to continue[/]")
        return True

    elif action == "security_blocked":
        config = ServerConfig.load()
        from darkcode_server.security import PersistentRateLimiter

        fancy_progress("Loading blocked IPs...", 5)

        db_path = config.config_dir / "security.db"
        if not db_path.exists():
            console.print("\n[dim]No security database yet.[/]")
        else:
            rate_limiter = PersistentRateLimiter(db_path)
            blocked = rate_limiter.get_blocked()

            console.print()
            if not blocked:
                console.print("[green]No blocked IPs or devices[/]")
            else:
                console.print("[bold red]Blocked[/]")
                for b in blocked:
                    console.print(f"  {b['identifier'][:20]} ({b['identifier_type']})")

        Prompt.ask("[dim]Press Enter to continue[/]")
        return True

    elif action == "security_unbind":
        config = ServerConfig.load()

        if not config.bound_device_id:
            console.print("\n[yellow]No device is currently bound.[/]")
        elif Confirm.ask("Unbind current device?", default=False):
            config.bound_device_id = None
            config.save()
            fancy_progress("Unbinding device...", 5)
            console.print("[green]Device unbound.[/]")

        Prompt.ask("[dim]Press Enter to continue[/]")
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
