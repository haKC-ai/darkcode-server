"""Interactive menu using questionary for clean, modern CLI experience."""

import os
import sys
from typing import Optional, Tuple

import questionary
from questionary import Style
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table
from rich import print as rprint

console = Console()

# Custom style - minimal, clean, no boxes
custom_style = Style([
    ('qmark', 'fg:#BD93F9 bold'),       # Purple question mark
    ('question', 'bold'),                # Question text
    ('answer', 'fg:#50FA7B bold'),       # Green answer
    ('pointer', 'fg:#FF79C6 bold'),      # Pink pointer
    ('highlighted', 'fg:#50FA7B bold'),  # Green highlighted
    ('selected', 'fg:#BD93F9'),          # Purple selected
    ('separator', 'fg:#6272A4'),         # Gray separator
    ('instruction', 'fg:#6272A4'),       # Gray instructions
    ('text', ''),                        # Normal text
])


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


def show_main_menu() -> Optional[str]:
    """Show main menu and get selection."""
    choices = [
        questionary.Choice("Start Server", value="start"),
        questionary.Choice("Server Status", value="status"),
        questionary.Choice("Show QR Code", value="qr"),
        questionary.Choice("Guest Codes", value="guest"),
        questionary.Choice("Configuration", value="config"),
        questionary.Choice("Security Settings", value="security"),
        questionary.Choice("Setup Wizard", value="setup"),
        questionary.Separator(),
        questionary.Choice("Quit", value="quit"),
    ]

    result = questionary.select(
        "What would you like to do?",
        choices=choices,
        style=custom_style,
        qmark="",
        pointer="",
        use_shortcuts=True,
        use_arrow_keys=True,
    ).ask()

    return None if result == "quit" else result


def show_connection_menu() -> Optional[str]:
    """Show connection mode selection."""
    from darkcode_server.config import ServerConfig
    config = ServerConfig.load()

    tailscale_ip = config.get_tailscale_ip()

    choices = [
        questionary.Choice("Direct LAN - Local network connection", value="direct"),
    ]

    if tailscale_ip:
        choices.append(questionary.Choice(f"Tailscale ({tailscale_ip}) - Secure mesh VPN", value="tailscale"))
    else:
        choices.append(questionary.Choice("Tailscale - Not detected", value="tailscale", disabled="not available"))

    choices.extend([
        questionary.Choice("SSH Tunnel - Localhost only, most secure", value="ssh"),
        questionary.Separator(),
        questionary.Choice("Back", value="back"),
    ])

    result = questionary.select(
        "Connection mode:",
        choices=choices,
        style=custom_style,
        qmark="",
        pointer="",
    ).ask()

    return None if result == "back" else result


def show_guest_menu() -> Optional[str]:
    """Show guest code management menu."""
    choices = [
        questionary.Choice("Create New Code", value="guest_create"),
        questionary.Choice("List All Codes", value="guest_list"),
        questionary.Choice("Revoke a Code", value="guest_revoke"),
        questionary.Choice("Show QR for Code", value="guest_qr"),
        questionary.Separator(),
        questionary.Choice("Back", value="back"),
    ]

    result = questionary.select(
        "Guest access:",
        choices=choices,
        style=custom_style,
        qmark="",
        pointer="",
    ).ask()

    return None if result == "back" else result


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
    console.print()

    choices = [
        questionary.Choice(f"Toggle TLS (currently {'ON' if config.tls_enabled else 'OFF'})", value="security_tls"),
        questionary.Choice(f"Toggle mTLS (currently {'ON' if config.mtls_enabled else 'OFF'})", value="security_mtls"),
        questionary.Choice(f"Toggle Device Lock (currently {'ON' if config.device_lock else 'OFF'})", value="security_device_lock"),
        questionary.Choice("Reset Auth Token", value="security_reset_token"),
        questionary.Choice("View Blocked IPs", value="security_blocked"),
        questionary.Choice("Unbind Device", value="security_unbind"),
        questionary.Separator(),
        questionary.Choice("Back", value="back"),
    ]

    result = questionary.select(
        "Security settings:",
        choices=choices,
        style=custom_style,
        qmark="",
        pointer="",
    ).ask()

    return None if result == "back" else result


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
        questionary.press_any_key_to_continue(
            message="Press any key to continue...",
            style=custom_style,
        ).ask()
        return True

    elif action == "qr":
        fancy_progress("Generating QR code...", 8)
        from darkcode_server.qrcode import print_server_info
        config = ServerConfig.load()
        console.print()
        print_server_info(config, console)
        console.print()
        questionary.press_any_key_to_continue(
            message="Press any key to continue...",
            style=custom_style,
        ).ask()
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

        if questionary.confirm("Edit configuration?", default=False, style=custom_style, qmark="").ask():
            new_port = questionary.text(
                "Port:",
                default=str(config.port),
                style=custom_style,
                qmark="",
            ).ask()

            new_dir = questionary.path(
                "Working directory:",
                default=str(config.working_dir),
                style=custom_style,
                qmark="",
            ).ask()

            new_name = questionary.text(
                "Server name:",
                default=config.server_name,
                style=custom_style,
                qmark="",
            ).ask()

            if new_port and new_dir and new_name:
                from pathlib import Path
                config.port = int(new_port)
                config.working_dir = Path(new_dir)
                config.server_name = new_name
                config.save()

                fancy_progress("Saving configuration...", 5)
                console.print("\n[green]Configuration saved![/]")

        questionary.press_any_key_to_continue(
            message="Press any key to continue...",
            style=custom_style,
        ).ask()
        return True

    elif action == "guest_create":
        console.print()
        console.print("[bold green]Create Guest Code[/]")
        console.print()

        name = questionary.text(
            "Friend's name:",
            style=custom_style,
            qmark="",
        ).ask()

        if not name:
            return True

        expires = questionary.text(
            "Expires in hours (0=never):",
            default="24",
            style=custom_style,
            qmark="",
        ).ask()

        max_uses = questionary.text(
            "Max uses (empty=unlimited):",
            default="",
            style=custom_style,
            qmark="",
        ).ask()

        read_only = questionary.confirm(
            "Read-only access?",
            default=False,
            style=custom_style,
            qmark="",
        ).ask()

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
        questionary.press_any_key_to_continue(
            message="Press any key to continue...",
            style=custom_style,
        ).ask()
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
        questionary.press_any_key_to_continue(
            message="Press any key to continue...",
            style=custom_style,
        ).ask()
        return True

    elif action == "guest_revoke":
        code = questionary.text(
            "Code to revoke:",
            style=custom_style,
            qmark="",
        ).ask()

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

        questionary.press_any_key_to_continue(
            message="Press any key to continue...",
            style=custom_style,
        ).ask()
        return True

    elif action == "guest_qr":
        code = questionary.text(
            "Code for QR:",
            style=custom_style,
            qmark="",
        ).ask()

        if not code:
            return True

        fancy_progress("Generating QR code...", 8)

        from darkcode_server.cli import guest_qr as show_guest_qr
        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(show_guest_qr, [code], standalone_mode=False)
        if result.output:
            console.print(result.output)

        questionary.press_any_key_to_continue(
            message="Press any key to continue...",
            style=custom_style,
        ).ask()
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

        questionary.press_any_key_to_continue(
            message="Press any key to continue...",
            style=custom_style,
        ).ask()
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

        questionary.press_any_key_to_continue(
            message="Press any key to continue...",
            style=custom_style,
        ).ask()
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

        questionary.press_any_key_to_continue(
            message="Press any key to continue...",
            style=custom_style,
        ).ask()
        return True

    elif action == "security_reset_token":
        if questionary.confirm(
            "Generate new auth token? Current connections will be invalidated.",
            default=False,
            style=custom_style,
            qmark="",
        ).ask():
            import secrets
            config = ServerConfig.load()
            config.token = secrets.token_urlsafe(24)
            config.save()

            fancy_progress("Generating new token...", 8)
            console.print(f"\n[green]New token:[/] {config.token}")

        questionary.press_any_key_to_continue(
            message="Press any key to continue...",
            style=custom_style,
        ).ask()
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

        questionary.press_any_key_to_continue(
            message="Press any key to continue...",
            style=custom_style,
        ).ask()
        return True

    elif action == "security_unbind":
        config = ServerConfig.load()

        if not config.bound_device_id:
            console.print("\n[yellow]No device is currently bound.[/]")
        elif questionary.confirm("Unbind current device?", default=False, style=custom_style, qmark="").ask():
            config.bound_device_id = None
            config.save()
            fancy_progress("Unbinding device...", 5)
            console.print("[green]Device unbound.[/]")

        questionary.press_any_key_to_continue(
            message="Press any key to continue...",
            style=custom_style,
        ).ask()
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
