"""Interactive menu using prompt_toolkit for arrow key navigation."""

import os
import sys
from pathlib import Path
from typing import Optional, Tuple, List, Any

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table

console = Console()


def clear_screen():
    """Clear the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')


def show_header():
    """Show app header with ASCII banner."""
    try:
        from hakcer import show_banner as hakcer_banner, set_theme
        set_theme("synthwave")

        banner_paths = [
            Path("/Users/0xdeadbeef/Desktop/darkcode.txt"),
            Path.home() / "darkcode" / ".darkcode" / "banner.txt",
            Path(__file__).parent / "assets" / "banner.txt",
        ]
        banner_file = next((p for p in banner_paths if p.exists()), None)

        if banner_file:
            hakcer_banner(custom_file=str(banner_file), effect_name="rain", hold_time=0.3)
        else:
            hakcer_banner(text="DARKCODE", effect_name="glitch", hold_time=0.2)
    except ImportError:
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
            time.sleep(0.03)
            progress.advance(task)


def get_random_theme_colors() -> dict:
    """Get colors from a random hakcer theme."""
    import random
    try:
        from hakcer import THEMES, list_themes
        theme_names = list_themes()
        theme_name = random.choice(theme_names)
        theme = THEMES[theme_name]
        colors = theme['colors']
        # Return primary colors for menu styling
        return {
            'title': f"#{colors['primary'][0]}",
            'selected': f"#{colors['primary'][1]}",
            'option': f"#{colors['accent'][0]}" if colors.get('accent') else '#888888',
            'hint': '#555555',
        }
    except ImportError:
        # Fallback if hakcer not installed
        return {
            'title': '#00D9FF',
            'selected': '#FF10F0',
            'option': '#888888',
            'hint': '#555555',
        }


def prompt_menu(title: str, options: List[Tuple[str, str]], back_option: bool = True) -> Optional[str]:
    """Show a menu using prompt_toolkit with arrow key navigation.

    Args:
        title: Menu title
        options: List of (value, display_text) tuples
        back_option: Whether to include back/quit option

    Returns:
        Selected value or None if back/quit
    """
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.keys import Keys
    from prompt_toolkit.application import Application
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.styles import Style

    if back_option:
        options = options + [("__back__", "[q] Back / Quit")]

    selected_index = [0]
    result = [None]

    # Get random theme colors for this menu
    theme_colors = get_random_theme_colors()

    kb = KeyBindings()

    @kb.add(Keys.Up)
    @kb.add('k')
    def move_up(event):
        selected_index[0] = (selected_index[0] - 1) % len(options)

    @kb.add(Keys.Down)
    @kb.add('j')
    def move_down(event):
        selected_index[0] = (selected_index[0] + 1) % len(options)

    @kb.add(Keys.Enter)
    def select(event):
        result[0] = options[selected_index[0]][0]
        event.app.exit()

    @kb.add('q')
    @kb.add(Keys.Escape)
    def quit_menu(event):
        result[0] = "__back__"
        event.app.exit()

    # Number key shortcuts
    for i in range(min(9, len(options))):
        num = str(i + 1)
        @kb.add(num)
        def select_num(event, idx=i):
            if idx < len(options):
                result[0] = options[idx][0]
                event.app.exit()

    def get_menu_text():
        lines = [('class:title', f'\n  {title}\n\n')]
        for i, (value, text) in enumerate(options):
            if i == selected_index[0]:
                lines.append(('class:selected', f'  > {text}\n'))
            else:
                lines.append(('class:option', f'    {text}\n'))
        lines.append(('class:hint', '\n  [arrows/jk] navigate  [enter] select  [q/esc] back\n'))
        return lines

    style = Style.from_dict({
        'title': f"bold {theme_colors['title']}",
        'selected': f"bold {theme_colors['selected']}",
        'option': theme_colors['option'],
        'hint': f"italic {theme_colors['hint']}",
    })

    layout = Layout(
        Window(content=FormattedTextControl(get_menu_text))
    )

    app = Application(layout=layout, key_bindings=kb, full_screen=False, style=style)
    app.run()

    if result[0] == "__back__":
        return None
    return result[0]


def prompt_input(label: str, default: str = "") -> str:
    """Prompt for text input."""
    from prompt_toolkit import prompt
    from prompt_toolkit.styles import Style

    style = Style.from_dict({'': 'cyan'})
    return prompt(f"  {label}: ", default=default, style=style)


def prompt_confirm(message: str, default: bool = False) -> bool:
    """Prompt for yes/no confirmation."""
    from prompt_toolkit import prompt
    hint = "[Y/n]" if default else "[y/N]"
    response = prompt(f"  {message} {hint}: ").strip().lower()
    if not response:
        return default
    return response in ('y', 'yes')


def show_status_table(data: dict):
    """Display status information as a clean table."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="white")

    for key, value in data.items():
        table.add_row(key, str(value))

    console.print()
    console.print(table)
    console.print()


# ============================================================================
# MAIN MENU
# ============================================================================

def show_main_menu() -> Optional[str]:
    """Show the main menu."""
    options = [
        ("start", "[1] Start Server"),
        ("daemon", "[2] Daemon Mode"),
        ("status", "[3] Server Status"),
        ("qr", "[4] Show QR Code"),
        ("guest", "[5] Guest Codes"),
        ("security", "[6] Security"),
        ("config", "[7] Configuration"),
        ("logs", "[8] View Logs"),
        ("service", "[9] System Service"),
    ]
    return prompt_menu("Main Menu", options)


# ============================================================================
# START SERVER
# ============================================================================

def show_start_menu() -> Optional[dict]:
    """Show start server options and return configuration."""
    from darkcode_server.config import ServerConfig
    config = ServerConfig.load()

    # Connection mode
    tailscale_ip = config.get_tailscale_ip()

    mode_options = [
        ("direct", "[1] Direct LAN - Local network"),
    ]
    if tailscale_ip:
        mode_options.append(("tailscale", f"[2] Tailscale ({tailscale_ip})"))
    else:
        mode_options.append(("tailscale_na", "[2] Tailscale (not detected)"))
    mode_options.append(("ssh", "[3] SSH Tunnel - Localhost only"))

    mode = prompt_menu("Connection Mode", mode_options)
    if mode is None or mode == "tailscale_na":
        return None

    # Additional options
    console.print()
    console.print("[cyan]  Server Options[/]")
    console.print()

    port = prompt_input("Port", str(config.port))
    working_dir = prompt_input("Working directory", str(config.working_dir))
    no_web = prompt_confirm("Disable web admin?", default=False)
    save_config = prompt_confirm("Save these settings?", default=False)

    return {
        "mode": mode,
        "port": int(port) if port else config.port,
        "working_dir": working_dir or str(config.working_dir),
        "no_web": no_web,
        "save": save_config,
    }


def show_daemon_menu() -> Optional[dict]:
    """Show daemon options."""
    options = [
        ("foreground", "[1] Start in foreground"),
        ("background", "[2] Start in background (detach)"),
        ("stop", "[3] Stop running daemon"),
    ]
    return prompt_menu("Daemon Mode", options)


# ============================================================================
# GUEST CODES
# ============================================================================

def show_guest_menu() -> Optional[str]:
    """Show guest code management menu."""
    options = [
        ("create", "[1] Create Guest Code"),
        ("list", "[2] List All Codes"),
        ("revoke", "[3] Revoke a Code"),
        ("qr", "[4] Show QR for Code"),
    ]
    return prompt_menu("Guest Access", options)


def show_guest_create_form() -> Optional[dict]:
    """Show form to create a guest code."""
    console.print()
    console.print("[cyan]  Create Guest Code[/]")
    console.print()

    name = prompt_input("Friend's name")
    if not name:
        return None

    expires = prompt_input("Expires in hours (0=never)", "24")
    max_uses = prompt_input("Max uses (empty=unlimited)", "")

    perm_options = [
        ("full", "[1] Full access"),
        ("read_only", "[2] Read-only"),
    ]
    permission = prompt_menu("Permission Level", perm_options, back_option=False)

    return {
        "name": name,
        "expires_hours": int(expires) if expires and expires != "0" else None,
        "max_uses": int(max_uses) if max_uses else None,
        "permission_level": permission or "full",
    }


# ============================================================================
# SECURITY
# ============================================================================

def show_security_menu() -> Optional[str]:
    """Show security settings menu."""
    from darkcode_server.config import ServerConfig
    config = ServerConfig.load()

    # Show current status inline
    console.print()
    tls = "[green]ON[/]" if config.tls_enabled else "[yellow]OFF[/]"
    mtls = "[green]ON[/]" if config.mtls_enabled else "[dim]OFF[/]"
    lock = "[green]ON[/]" if config.device_lock else "[yellow]OFF[/]"
    bound = config.bound_device_id[:12] + "..." if config.bound_device_id else "[dim]none[/]"

    console.print(f"  TLS: {tls}  |  mTLS: {mtls}  |  Device Lock: {lock}")
    console.print(f"  Bound Device: {bound}")

    options = [
        ("status", "[1] Full Security Status"),
        ("tls", f"[2] Toggle TLS ({'ON' if config.tls_enabled else 'OFF'})"),
        ("mtls", f"[3] Toggle mTLS ({'ON' if config.mtls_enabled else 'OFF'})"),
        ("device_lock", f"[4] Toggle Device Lock ({'ON' if config.device_lock else 'OFF'})"),
        ("unbind", "[5] Unbind Device"),
        ("reset_token", "[6] Reset Auth Token"),
        ("rotate_token", "[7] Rotate Token (scheduled)"),
        ("blocked", "[8] View Blocked IPs"),
        ("client_cert", "[9] Generate Client Certificate"),
    ]
    return prompt_menu("Security", options)


def show_tls_menu() -> Optional[dict]:
    """Show TLS configuration options."""
    options = [
        ("enable", "[1] Enable TLS"),
        ("disable", "[2] Disable TLS"),
        ("mtls_enable", "[3] Enable mTLS (client certs)"),
        ("mtls_disable", "[4] Disable mTLS"),
        ("regenerate", "[5] Regenerate Certificates"),
    ]
    return prompt_menu("TLS Configuration", options)


# ============================================================================
# CONFIGURATION
# ============================================================================

def show_config_menu() -> Optional[str]:
    """Show configuration menu."""
    options = [
        ("view", "[1] View Current Config"),
        ("edit", "[2] Edit Configuration"),
        ("token", "[3] Show Auth Token"),
        ("init", "[4] Re-initialize Config"),
    ]
    return prompt_menu("Configuration", options)


def show_config_edit_form() -> Optional[dict]:
    """Show configuration edit form."""
    from darkcode_server.config import ServerConfig
    config = ServerConfig.load()

    console.print()
    console.print("[cyan]  Edit Configuration[/]")
    console.print()

    port = prompt_input("Port", str(config.port))
    working_dir = prompt_input("Working directory", str(config.working_dir))
    server_name = prompt_input("Server name", config.server_name)
    max_sessions = prompt_input("Max sessions per IP", str(config.max_sessions_per_ip))

    if not prompt_confirm("Save changes?", default=True):
        return None

    return {
        "port": int(port) if port else config.port,
        "working_dir": working_dir,
        "server_name": server_name,
        "max_sessions_per_ip": int(max_sessions) if max_sessions else config.max_sessions_per_ip,
    }


# ============================================================================
# SERVICE / SYSTEM
# ============================================================================

def show_service_menu() -> Optional[str]:
    """Show system service options."""
    options = [
        ("install", "[1] Install as System Service"),
        ("uninstall", "[2] Uninstall Service"),
        ("setup", "[3] Run Setup Wizard"),
    ]
    return prompt_menu("System Service", options)


# ============================================================================
# ACTION HANDLERS
# ============================================================================

def execute_action(action: str, data: Any = None) -> bool:
    """Execute an action and return True to continue or False to exit."""
    from darkcode_server.config import ServerConfig

    if action == "status":
        config = ServerConfig.load()
        fancy_progress("Loading status...", 5)

        tailscale_ip = config.get_tailscale_ip()

        show_status_table({
            "Port": config.port,
            "Working Dir": str(config.working_dir),
            "Server Name": config.server_name,
            "TLS": "enabled" if config.tls_enabled else "disabled",
            "Device Lock": "enabled" if config.device_lock else "disabled",
            "Tailscale": tailscale_ip or "not detected",
        })

        # Check daemon
        try:
            from darkcode_server.daemon import DarkCodeDaemon
            pid = DarkCodeDaemon.get_running_pid(config)
            if pid:
                console.print(f"  [green]Daemon running (PID {pid})[/]")
            else:
                console.print("  [dim]Daemon not running[/]")
        except Exception:
            pass

        console.print()
        prompt_input("Press Enter to continue", "")
        return True

    elif action == "qr":
        fancy_progress("Generating QR code...", 8)
        from darkcode_server.qrcode import print_server_info
        config = ServerConfig.load()
        console.print()
        print_server_info(config, console)
        console.print()
        prompt_input("Press Enter to continue", "")
        return True

    elif action == "token":
        config = ServerConfig.load()
        console.print()
        console.print(f"  [cyan]Auth Token:[/] {config.token}")
        console.print()
        prompt_input("Press Enter to continue", "")
        return True

    elif action == "logs":
        config = ServerConfig.load()
        log_file = config.log_dir / "server.log"

        if not log_file.exists():
            console.print("\n  [yellow]No logs found.[/]\n")
        else:
            console.print(f"\n  [cyan]Tailing {log_file}...[/]")
            console.print("  [dim]Press Ctrl+C to stop[/]\n")
            try:
                import subprocess
                subprocess.run(["tail", "-f", str(log_file)])
            except KeyboardInterrupt:
                pass

        return True

    elif action == "view_config":
        config = ServerConfig.load()
        show_status_table({
            "Port": config.port,
            "Working Dir": str(config.working_dir),
            "Browse Dir": str(config.browse_dir) if config.browse_dir else "same as working",
            "Server Name": config.server_name,
            "Config Dir": str(config.config_dir),
            "Token": config.token[:4] + "*" * 16,
            "Max Sessions/IP": config.max_sessions_per_ip,
            "TLS Enabled": config.tls_enabled,
            "mTLS Enabled": config.mtls_enabled,
            "Device Lock": config.device_lock,
        })
        prompt_input("Press Enter to continue", "")
        return True

    elif action == "security_status":
        config = ServerConfig.load()
        fancy_progress("Loading security status...", 5)

        show_status_table({
            "Device Lock": "enabled" if config.device_lock else "disabled",
            "Bound Device": config.bound_device_id[:12] + "..." if config.bound_device_id else "none",
            "Idle Timeout": f"{config.idle_timeout}s" if config.idle_timeout > 0 else "disabled",
            "Local Only": "yes" if config.local_only else "no",
            "Rate Limit": f"{config.rate_limit_attempts} attempts / {config.rate_limit_window}s",
            "Max Sessions/IP": config.max_sessions_per_ip,
            "TLS Enabled": "yes (wss://)" if config.tls_enabled else "no (ws://)",
            "mTLS Enabled": "yes" if config.mtls_enabled else "no",
            "Token Rotation": f"{config.token_rotation_days} days" if config.token_rotation_days > 0 else "disabled",
        })

        # Check certs
        cert_dir = config.config_dir / "certs"
        server_cert = cert_dir / "server.crt"
        console.print(f"  Server Cert: {'[green]exists[/]' if server_cert.exists() else '[dim]not generated[/]'}")

        # Connection logs location
        console.print(f"\n  [cyan]Logs:[/] {config.log_dir}")
        console.print()
        prompt_input("Press Enter to continue", "")
        return True

    elif action == "blocked":
        config = ServerConfig.load()
        from darkcode_server.security import PersistentRateLimiter

        fancy_progress("Loading blocked IPs...", 5)

        db_path = config.config_dir / "security.db"
        if not db_path.exists():
            console.print("\n  [dim]No security database yet.[/]\n")
        else:
            rate_limiter = PersistentRateLimiter(db_path)
            blocked = rate_limiter.get_blocked()

            console.print()
            if not blocked:
                console.print("  [green]No blocked IPs or devices[/]")
            else:
                console.print("  [red]Blocked:[/]")
                for b in blocked:
                    console.print(f"    {b['identifier'][:20]} ({b['identifier_type']})")

        console.print()
        prompt_input("Press Enter to continue", "")
        return True

    elif action == "guest_list":
        config = ServerConfig.load()
        from darkcode_server.security import GuestAccessManager

        fancy_progress("Loading guest codes...", 5)

        guest_mgr = GuestAccessManager(config.config_dir / "guests.db")
        codes = guest_mgr.list_codes()

        console.print()
        if not codes:
            console.print("  [dim]No guest codes found.[/]")
        else:
            console.print("  [cyan]Guest Codes:[/]")
            for code in codes:
                status = "[green]active[/]"
                if not code.get("is_active"):
                    status = "[red]revoked[/]"
                elif code.get("expired"):
                    status = "[yellow]expired[/]"
                console.print(f"    [bold]{code['code']}[/] - {code['name']} ({status})")

        console.print()
        prompt_input("Press Enter to continue", "")
        return True

    return True


# ============================================================================
# MAIN MENU LOOP
# ============================================================================

def run_interactive_menu() -> Optional[Tuple[str, Optional[str]]]:
    """Run the interactive menu loop.

    Returns:
        Tuple of (action, mode) for actions that need to exit the menu,
        or None if user quit.
    """
    from darkcode_server.config import ServerConfig

    while True:
        clear_screen()
        show_header()

        action = show_main_menu()

        if action is None:
            return None

        # Start Server
        if action == "start":
            clear_screen()
            show_header()
            start_config = show_start_menu()
            if start_config:
                return ("start", start_config)
            continue

        # Daemon
        if action == "daemon":
            clear_screen()
            show_header()
            daemon_action = show_daemon_menu()
            if daemon_action == "foreground":
                return ("daemon_foreground", None)
            elif daemon_action == "background":
                return ("daemon_background", None)
            elif daemon_action == "stop":
                return ("daemon_stop", None)
            continue

        # Guest Codes
        if action == "guest":
            while True:
                clear_screen()
                show_header()
                guest_action = show_guest_menu()
                if guest_action is None:
                    break

                if guest_action == "create":
                    clear_screen()
                    show_header()
                    guest_data = show_guest_create_form()
                    if guest_data:
                        config = ServerConfig.load()
                        from darkcode_server.security import GuestAccessManager
                        guest_mgr = GuestAccessManager(config.config_dir / "guests.db")
                        fancy_progress("Creating guest code...", 8)
                        result = guest_mgr.create_guest_code(**guest_data)
                        console.print(f"\n  [green]Created![/] Code: [bold]{result['code']}[/]\n")
                        prompt_input("Press Enter to continue", "")

                elif guest_action == "list":
                    execute_action("guest_list")

                elif guest_action == "revoke":
                    console.print()
                    code = prompt_input("Code to revoke")
                    if code:
                        config = ServerConfig.load()
                        from darkcode_server.security import GuestAccessManager
                        guest_mgr = GuestAccessManager(config.config_dir / "guests.db")
                        fancy_progress("Revoking code...", 5)
                        if guest_mgr.revoke_code(code):
                            console.print(f"\n  [green]Revoked:[/] {code.upper()}\n")
                        else:
                            console.print(f"\n  [red]Not found:[/] {code}\n")
                        prompt_input("Press Enter to continue", "")

                elif guest_action == "qr":
                    console.print()
                    code = prompt_input("Code for QR")
                    if code:
                        fancy_progress("Generating QR...", 8)
                        from click.testing import CliRunner
                        from darkcode_server.cli import guest_qr
                        runner = CliRunner()
                        result = runner.invoke(guest_qr, [code], standalone_mode=False)
                        if result.output:
                            console.print(result.output)
                        prompt_input("Press Enter to continue", "")
            continue

        # Security
        if action == "security":
            while True:
                clear_screen()
                show_header()
                sec_action = show_security_menu()
                if sec_action is None:
                    break

                config = ServerConfig.load()

                if sec_action == "status":
                    execute_action("security_status")

                elif sec_action == "tls":
                    config.tls_enabled = not config.tls_enabled
                    config.save()
                    fancy_progress("Updating TLS...", 5)
                    status = "[green]enabled[/]" if config.tls_enabled else "[yellow]disabled[/]"
                    console.print(f"\n  TLS {status}\n")
                    prompt_input("Press Enter to continue", "")

                elif sec_action == "mtls":
                    config.mtls_enabled = not config.mtls_enabled
                    if config.mtls_enabled:
                        config.tls_enabled = True
                    config.save()
                    fancy_progress("Updating mTLS...", 5)
                    status = "[green]enabled[/]" if config.mtls_enabled else "[dim]disabled[/]"
                    console.print(f"\n  mTLS {status}\n")
                    prompt_input("Press Enter to continue", "")

                elif sec_action == "device_lock":
                    config.device_lock = not config.device_lock
                    config.save()
                    fancy_progress("Updating device lock...", 5)
                    status = "[green]enabled[/]" if config.device_lock else "[yellow]disabled[/]"
                    console.print(f"\n  Device Lock {status}\n")
                    prompt_input("Press Enter to continue", "")

                elif sec_action == "unbind":
                    if not config.bound_device_id:
                        console.print("\n  [yellow]No device is currently bound.[/]\n")
                    elif prompt_confirm("Unbind current device?"):
                        config.bound_device_id = None
                        config.save()
                        fancy_progress("Unbinding device...", 5)
                        console.print("\n  [green]Device unbound.[/]\n")
                    prompt_input("Press Enter to continue", "")

                elif sec_action == "reset_token":
                    if prompt_confirm("Generate new auth token? Current connections will be invalidated."):
                        import secrets
                        config.token = secrets.token_urlsafe(24)
                        config.save()
                        fancy_progress("Generating new token...", 8)
                        console.print(f"\n  [green]New token:[/] {config.token}\n")
                    prompt_input("Press Enter to continue", "")

                elif sec_action == "rotate_token":
                    return ("rotate_token", None)

                elif sec_action == "blocked":
                    execute_action("blocked")

                elif sec_action == "client_cert":
                    console.print()
                    device_id = prompt_input("Device ID for certificate")
                    if device_id:
                        return ("client_cert", device_id)
            continue

        # Configuration
        if action == "config":
            while True:
                clear_screen()
                show_header()
                cfg_action = show_config_menu()
                if cfg_action is None:
                    break

                if cfg_action == "view":
                    execute_action("view_config")

                elif cfg_action == "edit":
                    clear_screen()
                    show_header()
                    edit_data = show_config_edit_form()
                    if edit_data:
                        config = ServerConfig.load()
                        config.port = edit_data["port"]
                        config.working_dir = Path(edit_data["working_dir"])
                        config.server_name = edit_data["server_name"]
                        config.max_sessions_per_ip = edit_data["max_sessions_per_ip"]
                        config.save()
                        fancy_progress("Saving configuration...", 5)
                        console.print("\n  [green]Configuration saved![/]\n")
                    prompt_input("Press Enter to continue", "")

                elif cfg_action == "token":
                    execute_action("token")

                elif cfg_action == "init":
                    return ("setup", None)
            continue

        # Logs
        if action == "logs":
            execute_action("logs")
            continue

        # Service
        if action == "service":
            clear_screen()
            show_header()
            svc_action = show_service_menu()
            if svc_action == "install":
                return ("install", None)
            elif svc_action == "uninstall":
                return ("uninstall", None)
            elif svc_action == "setup":
                return ("setup", None)
            continue

        # Status (quick)
        if action == "status":
            execute_action("status")
            continue

        # QR code
        if action == "qr":
            execute_action("qr")
            continue
